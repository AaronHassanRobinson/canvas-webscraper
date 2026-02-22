from canvasapi import Canvas
import argparse
import os
import re
import sys
import time

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn, TaskProgressColumn
from rich.panel import Panel
from rich.table import Table

# Rich console for colored output
console = Console()

# Track failed and skipped downloads for reporting at end
failed_downloads = []
skipped_files = []
downloaded_files = []
MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds between retries
DEFAULT_CONFIG_FILE = "canvas_credentials.txt"

# Download mode (set by CLI args)
DOWNLOAD_MODE = "resume"  # "resume" = skip existing, "force" = redownload all

# Global progress bar reference
progress = None
overall_task = None


def load_config_from_file(config_path):
    """Load configuration from a file. Returns dict with API_URL, API_KEY, DOWNLOAD_DIR."""
    config = {}
    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    except FileNotFoundError:
        return None
    return config


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Download all course content from Canvas LMS.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python main.py                          # Resume mode - skip existing files
  python main.py --force                  # Force redownload all files
  python main.py -c my_config.txt         # Use custom config file
  python main.py --url https://canvas.edu --key YOUR_API_KEY --output downloads

Config file format (canvas_credentials.txt):
  API_URL=https://your-canvas-instance.edu
  API_KEY=your_api_key_here
  DOWNLOAD_DIR=output_folder_name
'''
    )
    parser.add_argument('-c', '--config',
                        help=f'Path to config file (default: {DEFAULT_CONFIG_FILE})',
                        default=None)
    parser.add_argument('-u', '--url',
                        help='Canvas API URL (e.g., https://canvas.instructure.com)')
    parser.add_argument('-k', '--key',
                        help='Canvas API key')
    parser.add_argument('-o', '--output',
                        help='Output directory for downloads')
    parser.add_argument('-r', '--resume', action='store_true', default=True,
                        help='Skip files that already exist (default behavior)')
    parser.add_argument('-f', '--force', action='store_true',
                        help='Force redownload of all files, overwriting existing')
    return parser.parse_args()


def get_config():
    """Get configuration from CLI args or config file."""
    global DOWNLOAD_MODE
    args = parse_arguments()

    # Set download mode
    if args.force:
        DOWNLOAD_MODE = "force"
    else:
        DOWNLOAD_MODE = "resume"

    # If all CLI args provided, use them
    if args.url and args.key and args.output:
        return {
            'API_URL': args.url,
            'API_KEY': args.key,
            'DOWNLOAD_DIR': args.output
        }

    # Try to load from config file
    config_path = args.config if args.config else DEFAULT_CONFIG_FILE
    config = load_config_from_file(config_path)

    if config is None:
        if args.config:
            console.print(f"[red]Error:[/red] Config file '{args.config}' not found.")
        else:
            console.print(f"[red]Error:[/red] No config file found and missing CLI arguments.")
            console.print(f"Either create '[cyan]{DEFAULT_CONFIG_FILE}[/cyan]' or provide --url, --key, and --output arguments.")
            console.print("Run with [cyan]-h[/cyan] for help.")
        sys.exit(1)

    # CLI args override config file
    if args.url:
        config['API_URL'] = args.url
    if args.key:
        config['API_KEY'] = args.key
    if args.output:
        config['DOWNLOAD_DIR'] = args.output

    # Validate required fields
    required = ['API_URL', 'API_KEY', 'DOWNLOAD_DIR']
    missing = [r for r in required if r not in config or not config[r]]
    if missing:
        console.print(f"[red]Error:[/red] Missing required config values: {', '.join(missing)}")
        sys.exit(1)

    return config


def should_skip_file(file_path):
    """Check if file should be skipped based on download mode."""
    if DOWNLOAD_MODE == "force":
        return False
    return os.path.exists(file_path) and os.path.getsize(file_path) > 0


def update_status(message, style="white"):
    """Update the current status message."""
    if progress:
        progress.console.print(f"[{style}]{message}[/{style}]")


def download_file_with_retry(url, file_path, description):
    """Download a file with retry logic and progress bar. Returns True if successful, False otherwise."""
    global progress

    # Check if file exists and should be skipped
    if should_skip_file(file_path):
        update_status(f"[dim]Skipped (exists):[/dim] {description}", "yellow")
        skipped_files.append({'file': description, 'path': file_path})
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with requests.get(url, stream=True, timeout=30) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))

                # Create a download task for this file
                if progress and total_size > 0:
                    download_task = progress.add_task(
                        f"[cyan]{description[:50]}...[/cyan]" if len(description) > 50 else f"[cyan]{description}[/cyan]",
                        total=total_size
                    )

                    with open(file_path, 'wb') as f:
                        downloaded = 0
                        for chunk in response.iter_content(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            progress.update(download_task, completed=downloaded)

                    progress.remove_task(download_task)
                else:
                    # No content-length, download without per-file progress
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(8192):
                            f.write(chunk)

            update_status(f"[green]Downloaded:[/green] {description}", "green")
            downloaded_files.append({'file': description, 'path': file_path})
            return True
        except requests.exceptions.RequestException as e:
            update_status(f"[red]Attempt {attempt}/{MAX_RETRIES} failed for {description}[/red]", "red")
            if attempt < MAX_RETRIES:
                update_status(f"[yellow]Retrying in {RETRY_DELAY} seconds...[/yellow]", "yellow")
                time.sleep(RETRY_DELAY)
            else:
                update_status(f"[red]All {MAX_RETRIES} attempts failed for {description}[/red]", "red")
                failed_downloads.append({
                    'file': description,
                    'path': file_path,
                    'error': str(e)
                })
                return False
    return False


def download_canvas_file_with_retry(canvas_file, file_path, description):
    """Download a Canvas file object with retry logic."""
    # Check if file exists and should be skipped
    if should_skip_file(file_path):
        update_status(f"[dim]Skipped (exists):[/dim] {description}", "yellow")
        skipped_files.append({'file': description, 'path': file_path})
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            canvas_file.download(file_path)
            update_status(f"[green]Downloaded:[/green] {description}", "green")
            downloaded_files.append({'file': description, 'path': file_path})
            return True
        except Exception as e:
            update_status(f"[red]Attempt {attempt}/{MAX_RETRIES} failed for {description}[/red]", "red")
            if attempt < MAX_RETRIES:
                update_status(f"[yellow]Retrying in {RETRY_DELAY} seconds...[/yellow]", "yellow")
                time.sleep(RETRY_DELAY)
            else:
                update_status(f"[red]All {MAX_RETRIES} attempts failed for {description}[/red]", "red")
                failed_downloads.append({
                    'file': description,
                    'path': file_path,
                    'error': str(e)
                })
                return False
    return False


# Load configuration
config = get_config()
API_URL = config['API_URL']
API_KEY = config['API_KEY']
download_directory = config['DOWNLOAD_DIR']

# Display banner
console.print(Panel.fit(
    "[bold cyan]Canvas LMS Scraper[/bold cyan]\n"
    f"[dim]Output: {download_directory}[/dim]",
    border_style="cyan"
))

mode_color = "red" if DOWNLOAD_MODE == "force" else "green"
mode_text = "FORCE (redownload all)" if DOWNLOAD_MODE == "force" else "RESUME (skip existing)"
console.print(f"Mode: [{mode_color}]{mode_text}[/{mode_color}]")


def make_directory(directory_name: str):
    if not os.path.exists(directory_name):
        try:
            os.makedirs(directory_name)
        except:
            console.print(f"[red]Error making folder: {directory_name}[/red]")
            exit()
    return


# Parse a string before turning it into a dir, returns a str:
def sanitize_string(directory_name: str) -> str:
    # Remove characters illegal on Windows: < > : " / \ | ? * and also [ ] ( ) ' ,
    parsed_symbols = re.sub(r'[\[\]()<>:?\*\\\/\"\'\,|]', "", directory_name)
    # Replace spaces with underscores
    remove_spaces = re.sub(" ", "_", parsed_symbols)
    # Remove trailing dots and spaces (illegal on Windows)
    cleaned = remove_spaces.rstrip(". ")
    return cleaned if cleaned else "unnamed"


make_directory(download_directory)

# Connect to Canvas
with console.status("[bold green]Connecting to Canvas...[/bold green]", spinner="dots"):
    try:
        canvas = Canvas(API_URL, API_KEY)
        user = canvas.get_current_user()
    except Exception as e:
        console.print(f"[red]Error connecting to Canvas: {e}[/red]")
        exit()

console.print(f"[green]Connected![/green] Logged in as: [cyan]{user.name}[/cyan]")

# Get courses
with console.status("[bold green]Fetching courses...[/bold green]", spinner="dots"):
    courses = list(canvas.get_courses())
    course_count = sum(1 for c in courses if hasattr(c, "name"))

console.print(f"Found [cyan]{course_count}[/cyan] courses\n")

# Main download loop with progress
with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(bar_width=40),
    TaskProgressColumn(),
    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    DownloadColumn(),
    TransferSpeedColumn(),
    TimeRemainingColumn(),
    console=console,
    expand=False
) as progress_bar:
    progress = progress_bar

    # Overall progress task
    overall_task = progress_bar.add_task(
        "[bold blue]Overall Progress[/bold blue]",
        total=course_count
    )

    course_num = 0
    for course in courses:
        if hasattr(course, "name"):
            course_num += 1
            course_name = course.name

            # Update overall progress description
            progress_bar.update(overall_task, description=f"[bold blue]Course {course_num}/{course_count}:[/bold blue] {course_name[:40]}...")

            class_name = sanitize_string(course_name)
            course_download_path = os.path.join(download_directory, class_name)
            make_directory(course_download_path)

            # Now we want to setup the dir to follow canvas structure:
            try:
                modules = course.get_modules()
                for module in modules:
                    module_name = sanitize_string(module.name)
                    module_course_download_path = os.path.join(course_download_path, module_name)
                    make_directory(module_course_download_path)

                    # grab every item in the modules
                    module_items = module.get_module_items()
                    GotAssignmentFlag = 0
                    for item in module_items:
                        match item.type:
                            case 'Page':
                                page_url = item.page_url
                                page = course.get_page(page_url)

                                page_file_name = sanitize_string(f'{page.title}.html')
                                page_file_path = os.path.join(module_course_download_path, page_file_name)

                                if should_skip_file(page_file_path):
                                    update_status(f"[dim]Skipped (exists):[/dim] {page_file_name}", "yellow")
                                    skipped_files.append({'file': page_file_name, 'path': page_file_path})
                                    break

                                with open(page_file_path, 'w', encoding='utf-8') as f:
                                    f.write(f'<html><head><title>{page.title}</title></head><body>')
                                    f.write(page.body if getattr(page, "body") else "")
                                    f.write("</body></html>")

                                update_status(f"[green]Saved page:[/green] {page_file_name}", "green")
                                downloaded_files.append({'file': page_file_name, 'path': page_file_path})
                                break
                            case 'File':
                                file_id = item.content_id
                                file = course.get_file(file_id)
                                file_name = sanitize_string(file.display_name)
                                file_path = os.path.join(module_course_download_path, file_name)
                                download_canvas_file_with_retry(file, file_path, file_name)
                                break

                            case 'Assignment':
                                GotAssignmentFlag = 1
                                assignment_id = item.content_id
                                assignment = course.get_assignment(assignment_id)

                                assignment_folder = os.path.join(module_course_download_path,
                                                                 sanitize_string(assignment.name))

                                make_directory(assignment_folder)

                                assignment_description_path = os.path.join(assignment_folder, "assignment_description.html")
                                with open(assignment_description_path, 'w', encoding='utf-8') as f:
                                    f.write(f"<h1>{assignment.name}</h1>")
                                    f.write(f"<p>Due: {getattr(assignment, 'due_at', 'No due date')}</p>")
                                    f.write(f"<p>Points: {getattr(assignment, 'points_possible', 'N/A')}</p>")
                                    f.write(assignment.description if assignment.description else "")

                                submission = assignment.get_submission(user)
                                sub_path = os.path.join(assignment_folder, "my_submission.txt")
                                with open(sub_path, 'w', encoding='utf-8') as f:
                                    f.write(f"Submitted at: {getattr(submission, 'submitted_at', 'Not submitted')}\n")
                                    f.write(f"Grade: {getattr(submission, 'grade', 'Not graded')}\n")
                                    f.write(f"Score: {getattr(submission, 'score', 'N/A')}\n\n")

                                    if hasattr(submission, 'submission_comments'):
                                        f.write("Comments:\n")
                                        for comment in submission.submission_comments:
                                            f.write(f"  - {comment.get('author_name', 'Unknown')}: {comment.get('comment', '')}\n")

                                    if hasattr(submission, 'attachments') and submission.attachments:
                                        for attachment in submission.attachments:
                                            file_path = os.path.join(assignment_folder, attachment.filename)
                                            description = f"{attachment.filename} (from {assignment.name})"
                                            download_file_with_retry(attachment.url, file_path, description)

                                    if hasattr(submission, 'body') and submission.body:
                                        text_path = os.path.join(assignment_folder, "submission_text.html")
                                        with open(text_path, 'w', encoding='utf-8') as f:
                                            f.write(submission.body)

                                update_status(f"[green]Saved assignment:[/green] {assignment.name[:50]}", "green")
                                break
                            case 'Discussion':
                                discussion_id = item.content_id
                                discussion = course.get_discussion_topic(discussion_id)

                                file_name = sanitize_string(f"{discussion.title}.html")
                                file_path = os.path.join(module_course_download_path, file_name)

                                if should_skip_file(file_path):
                                    update_status(f"[dim]Skipped (exists):[/dim] {file_name}", "yellow")
                                    skipped_files.append({'file': file_name, 'path': file_path})
                                    break

                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(f"<h1>{discussion.title}</h1>")
                                    f.write(f"<p>Posted: {getattr(discussion, 'posted_at', 'unknown')}</p>")
                                    f.write(f"<div>{discussion.message if discussion.message else ''}</div>")
                                    f.write(f"<h2>Discussion entries:</h2>")
                                    try:
                                        entries = discussion.get_topic_entries()
                                        for entry in entries:
                                            f.write(f"<div style='margin: 20px;'>")
                                            f.write(f"<strong>{getattr(entry, 'user_name', 'Unknown')}</strong><br>")
                                            f.write(f"{getattr(entry, 'message', '')}")
                                            f.write(f"</div>")
                                    except Exception as e:
                                        f.write(f"<p>Could not load entries, error: {e}</p>")

                                update_status(f"[green]Saved discussion:[/green] {file_name}", "green")
                                downloaded_files.append({'file': file_name, 'path': file_path})
                                break
                            case 'ExternalUrl':
                                file_name = sanitize_string(f"{item.title}_link.txt")
                                file_path = os.path.join(module_course_download_path, file_name)

                                if should_skip_file(file_path):
                                    update_status(f"[dim]Skipped (exists):[/dim] {file_name}", "yellow")
                                    skipped_files.append({'file': file_name, 'path': file_path})
                                    break

                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(f"Title: {item.title}\n")
                                    f.write(f"URL: {item.external_url}\n")
                                update_status(f"[green]Saved URL:[/green] {file_name}", "green")
                                downloaded_files.append({'file': file_name, 'path': file_path})
                                break
                            case 'ExternalTool':
                                file_name = sanitize_string(f"{item.title}_external_tool.txt")
                                file_path = os.path.join(module_course_download_path, file_name)

                                if should_skip_file(file_path):
                                    update_status(f"[dim]Skipped (exists):[/dim] {file_name}", "yellow")
                                    skipped_files.append({'file': file_name, 'path': file_path})
                                    break

                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(f"Title: {item.title}\n")
                                    f.write(f"URL: {item.external_url}\n")
                                update_status(f"[green]Saved external tool:[/green] {file_name}", "green")
                                downloaded_files.append({'file': file_name, 'path': file_path})
                                break
                            case 'SubHeader':
                                break
                            case "Quiz":
                                quiz_id = item.content_id
                                try:
                                    quiz = course.get_quiz(quiz_id)
                                    quiz_folder = os.path.join(module_course_download_path,
                                                               sanitize_string(quiz.title))
                                    make_directory(quiz_folder)

                                    # Save quiz details
                                    quiz_info_path = os.path.join(quiz_folder, "quiz_info.html")
                                    if should_skip_file(quiz_info_path):
                                        update_status(f"[dim]Skipped (exists):[/dim] {quiz.title}", "yellow")
                                        skipped_files.append({'file': quiz.title, 'path': quiz_info_path})
                                        break

                                    with open(quiz_info_path, 'w', encoding='utf-8') as f:
                                        f.write(f"<html><head><title>{quiz.title}</title></head><body>")
                                        f.write(f"<h1>{quiz.title}</h1>")
                                        f.write(f"<p><strong>Due:</strong> {getattr(quiz, 'due_at', 'No due date')}</p>")
                                        f.write(f"<p><strong>Points:</strong> {getattr(quiz, 'points_possible', 'N/A')}</p>")
                                        f.write(f"<p><strong>Time Limit:</strong> {getattr(quiz, 'time_limit', 'None')} minutes</p>")
                                        f.write(f"<p><strong>Allowed Attempts:</strong> {getattr(quiz, 'allowed_attempts', 'Unlimited')}</p>")
                                        f.write(f"<h2>Description</h2>")
                                        f.write(f"<div>{quiz.description if quiz.description else 'No description'}</div>")
                                        f.write("</body></html>")

                                    downloaded_files.append({'file': f"{quiz.title}/quiz_info.html", 'path': quiz_info_path})

                                    # Try to get quiz questions
                                    try:
                                        questions = quiz.get_questions()
                                        questions_path = os.path.join(quiz_folder, "quiz_questions.html")
                                        with open(questions_path, 'w', encoding='utf-8') as f:
                                            f.write(f"<html><head><title>{quiz.title} - Questions</title></head><body>")
                                            f.write(f"<h1>{quiz.title} - Questions</h1>")
                                            q_num = 0
                                            for question in questions:
                                                q_num += 1
                                                f.write(f"<div style='margin: 20px 0; padding: 15px; border: 1px solid #ccc;'>")
                                                f.write(f"<h3>Question {q_num}</h3>")
                                                f.write(f"<p><strong>Type:</strong> {getattr(question, 'question_type', 'Unknown')}</p>")
                                                f.write(f"<p><strong>Points:</strong> {getattr(question, 'points_possible', 'N/A')}</p>")
                                                f.write(f"<div>{getattr(question, 'question_text', '')}</div>")

                                                # Show answers/choices if available
                                                if hasattr(question, 'answers') and question.answers:
                                                    f.write("<ul>")
                                                    for answer in question.answers:
                                                        answer_text = answer.get('text', answer.get('html', ''))
                                                        f.write(f"<li>{answer_text}</li>")
                                                    f.write("</ul>")
                                                f.write("</div>")
                                            f.write("</body></html>")
                                        downloaded_files.append({'file': f"{quiz.title}/quiz_questions.html", 'path': questions_path})
                                    except Exception:
                                        pass  # Questions may not be accessible

                                    # Try to get user's quiz submission
                                    try:
                                        submissions = quiz.get_submissions()
                                        for submission in submissions:
                                            if getattr(submission, 'user_id', None) == user.id:
                                                sub_path = os.path.join(quiz_folder, "my_submission.html")
                                                with open(sub_path, 'w', encoding='utf-8') as f:
                                                    f.write(f"<html><head><title>{quiz.title} - My Submission</title></head><body>")
                                                    f.write(f"<h1>{quiz.title} - My Submission</h1>")
                                                    f.write(f"<p><strong>Score:</strong> {getattr(submission, 'score', 'N/A')} / {getattr(quiz, 'points_possible', 'N/A')}</p>")
                                                    f.write(f"<p><strong>Attempt:</strong> {getattr(submission, 'attempt', 'N/A')}</p>")
                                                    f.write(f"<p><strong>Submitted:</strong> {getattr(submission, 'finished_at', 'N/A')}</p>")
                                                    f.write(f"<p><strong>Time Spent:</strong> {getattr(submission, 'time_spent', 'N/A')} seconds</p>")
                                                    f.write("</body></html>")
                                                downloaded_files.append({'file': f"{quiz.title}/my_submission.html", 'path': sub_path})
                                                break
                                    except Exception:
                                        pass  # Submissions may not be accessible

                                    update_status(f"[green]Saved quiz:[/green] {quiz.title}", "green")
                                except Exception as e:
                                    update_status(f"[red]Error getting quiz: {e}[/red]", "red")
                                break
                            case _:
                                update_status(f"[yellow]Unknown type:[/yellow] {item.type}", "yellow")
                        pass
                GotAssignmentFlag = 0
                if GotAssignmentFlag == 0:
                    assignments = course.get_assignments()
                    for assignment in assignments:
                        assignment_download_path = os.path.join(course_download_path, 'ASSIGNMENTS')

                        assignment_folder = os.path.join(assignment_download_path,
                                                            sanitize_string(assignment.name))

                        make_directory(assignment_folder)

                        assignment_description_path = os.path.join(assignment_folder, "assignment_description.html")
                        with open(assignment_description_path, 'w', encoding='utf-8') as f:
                            f.write(f"<h1>{assignment.name}</h1>")
                            f.write(f"<p>Due: {getattr(assignment, 'due_at', 'No due date')}</p>")
                            f.write(f"<p>Points: {getattr(assignment, 'points_possible', 'N/A')}</p>")
                            f.write(assignment.description if assignment.description else "")

                        submission = assignment.get_submission(user, include=['group', 'submission_history'])
                        sub_path = os.path.join(assignment_folder, "my_submission.txt")
                        with open(sub_path, 'w', encoding='utf-8') as f:
                            f.write(f"Submitted at: {getattr(submission, 'submitted_at', 'Not submitted')}\n")
                            f.write(f"Grade: {getattr(submission, 'grade', 'Not graded')}\n")
                            f.write(f"Score: {getattr(submission, 'score', 'N/A')}\n\n")

                            if hasattr(submission, 'submission_comments'):
                                f.write("Comments:\n")
                                for comment in submission.submission_comments:
                                    f.write(f"  - {comment.get('author_name', 'Unknown')}: {comment.get('comment', '')}\n")

                            if hasattr(submission, 'attachments') and submission.attachments:
                                for attachment in submission.attachments:
                                    file_path = os.path.join(assignment_folder, attachment.filename)
                                    description = f"{attachment.filename} (from {assignment.name})"
                                    download_file_with_retry(attachment.url, file_path, description)

                            if hasattr(submission, 'body') and submission.body:
                                text_path = os.path.join(assignment_folder, "submission_text.html")
                                with open(text_path, 'w', encoding='utf-8') as f:
                                    f.write(submission.body)
            except Exception as e:
                update_status(f"[red]Error processing course {course_name}: {e}[/red]", "red")

            # Update overall progress
            progress_bar.update(overall_task, advance=1)

# Calculate stats
def get_directory_stats(directory):
    """Get stats about the download directory."""
    total_size = 0
    file_count = 0
    folder_count = 0
    file_types = {}

    for root, dirs, files in os.walk(directory):
        folder_count += len(dirs)
        for file in files:
            file_path = os.path.join(root, file)
            try:
                size = os.path.getsize(file_path)
                total_size += size
                file_count += 1

                # Track file types
                ext = os.path.splitext(file)[1].lower() or '.other'
                file_types[ext] = file_types.get(ext, 0) + 1
            except OSError:
                pass

    return total_size, file_count, folder_count, file_types


def format_size(size_bytes):
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# Get directory stats
total_size, file_count, folder_count, file_types = get_directory_stats(download_directory)

# Print summary
console.print()
console.print(Panel.fit(
    "[bold green]✓ DOWNLOAD COMPLETE[/bold green]",
    border_style="green"
))

# Main stats table
stats_table = Table(show_header=False, box=None, padding=(0, 2))
stats_table.add_column("Label", style="bold")
stats_table.add_column("Value", justify="right")

stats_table.add_row("[green]Downloaded[/green]", f"[green]{len(downloaded_files)}[/green]")
stats_table.add_row("[yellow]Skipped[/yellow]", f"[yellow]{len(skipped_files)}[/yellow]")
stats_table.add_row("[red]Failed[/red]", f"[red]{len(failed_downloads)}[/red]")
stats_table.add_row("", "")
stats_table.add_row("[cyan]Total Files[/cyan]", f"[cyan]{file_count}[/cyan]")
stats_table.add_row("[cyan]Total Folders[/cyan]", f"[cyan]{folder_count}[/cyan]")
stats_table.add_row("[cyan]Total Size[/cyan]", f"[cyan]{format_size(total_size)}[/cyan]")

console.print(stats_table)

# File type breakdown (top 5)
if file_types:
    console.print()
    sorted_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:6]

    type_table = Table(title="[bold]File Types[/bold]", box=None, show_header=False, padding=(0, 1))
    type_table.add_column("Type", style="dim")
    type_table.add_column("Count", justify="right")
    type_table.add_column("Bar")

    max_count = sorted_types[0][1] if sorted_types else 1
    for ext, count in sorted_types:
        bar_width = int((count / max_count) * 20)
        bar = "█" * bar_width
        color = {"pdf": "red", ".html": "blue", ".txt": "white", ".docx": "blue", ".zip": "yellow"}.get(ext, "cyan")
        type_table.add_row(ext, str(count), f"[{color}]{bar}[/{color}]")

    console.print(type_table)

# Show failed downloads if any
if failed_downloads:
    console.print()
    console.print("[bold red]Failed downloads:[/bold red]")
    for item in failed_downloads[:5]:  # Limit to first 5
        console.print(f"  [red]•[/red] {item['file'][:60]}...")
        console.print(f"    [dim]{item['error'][:60]}...[/dim]")
    if len(failed_downloads) > 5:
        console.print(f"  [dim]... and {len(failed_downloads) - 5} more[/dim]")

# Simple directory summary instead of full tree
console.print()
console.print(f"[dim]Output directory:[/dim] [cyan]{os.path.abspath(download_directory)}[/cyan]")

