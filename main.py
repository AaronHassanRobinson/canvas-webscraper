from canvasapi import Canvas
import os
import re

import requests

print("Connecting to Canvas...")

API_URL = "https://uclearn.canberra.edu.au"

API_KEY = "10484~CEnQHvQZ8JF3Ye6ckPMXQrtnah2erKRwAxkCreNBV76nyZVtnJP2z7CvwGtn3LTX"

download_directory = "University_Engineering_Honours"


def make_directory(directory_name: str):

    if not os.path.exists(directory_name):
        try:
            os.makedirs(directory_name)
        except:
            print("Error making folder")
            exit()
    print(f"Creating directory: {directory_name}")
    return


# Parse a string before turning it into a dir, returns a str:
def sanitize_string(directory_name: str) -> str:

    parsed_symbols = re.sub(r"[\[\]()<>\?\*\\\/\"\',]", "", directory_name)
    remove_spaces = re.sub(" ", "_", parsed_symbols)
    return remove_spaces

make_directory(download_directory)


try:
    canvas = Canvas(API_URL, API_KEY)
except:
    print("Error occurred connecting to canvas :(")
    exit()

print("Successfully created canvas object")

user = canvas.get_current_user()
print(f"Username: {user.name}")

courses = canvas.get_courses()

for course in courses:
    if hasattr(course, "name"):
        course_name = course.name
        print(f"{course.name}\n")
        # Lets replace all the spaces with '_' and remove all commas (just gonna do all special chars to be safe)
        class_name = sanitize_string(course_name)
        print(f"Creating directory: {class_name}")
        course_download_path = f'{download_directory}//{class_name}'
        make_directory(course_download_path)

        # # Now we want to setup the dir to follow canvas structure:
        # modules = course.get_modules()
        # for module in modules:
        #     print(module.name)
        #     module_name = sanitize_string(module.name)
        #     module_course_download_path = f'{course_download_path}//{module_name}'
        #     make_directory(module_course_download_path)

        #     # grab every item in the modules 
        #     module_items = module.get_module_items()
        #     GotAssignmentFlag = 0
        #     for item in module_items:
        #         match item.type:
        #             case 'Page':
        #                 # I think it would be cool to save the pages as html, so I will do that lolz
        #                 page_url = item.page_url
        #                 page = course.get_page(page_url)

        #                 page_file_name = sanitize_string(f'{page.title}.html')
        #                 page_file_path = os.path.join(module_course_download_path, page_file_name)

        #                 # # Unfortunately this doesn't scrape css or js. Perhaps something to look into in the future...
        #                 with open(page_file_path, 'w', encoding='utf-8') as f:
        #                     f.write(f'<html><head><title>{page.title}</title></head><body>')
        #                    #Exception has occurred: AttributeError
        #                     #'Page' object has no attribute 'body' need to fix
        #                     f.write(page.body if getattr(page, "body") else "")
        #                     f.write("</body></html>")
                        
        #                 print(f"Saved page as: {page_file_name} in {module_course_download_path}")
        #                 pass
        #                 break
        #             case 'File':
        #                 file_id = item.content_id
        #                 file = course.get_file(file_id)
        #                 file_name = sanitize_string(file.display_name)
        #                 file_path = os.path.join(module_course_download_path, file_name)
        #                 file.download(file_path)
        #                 print(f"Downloaded: {file_name}")
        #                 break

        #             ### Might need to do this separately just in case... 
        #             case 'Assignment':
        #                 GotAssignmentFlag = 1
        #                 breakpoint()
        #                 assignment_id = item.content_id
        #                 assignment = course.get_assignment(assignment_id)

        #                 assignment_folder = os.path.join(module_course_download_path,
        #                                                  sanitize_string(assignment.name))
                        
        #                 make_directory(assignment_folder)

        #                 # Save assignment description as html page (todo): look if there is a better format for this
        #                 assignment_description_path = os.path.join(assignment_folder, "assignment_description.html")
        #                 with open(assignment_description_path, 'w', encoding='utf-8') as f:
        #                     f.write(f"<h1>{assignment.name}</h1>")
        #                     f.write(f"<p>Due: {getattr(assignment, 'due_at', 'No due date')}</p>")
        #                     f.write(f"<p>Points: {getattr(assignment, 'points_possible', 'N/A')}</p>")
        #                     f.write(assignment.description if assignment.description else "")

        #                 # Get submission(s): (todo):there is a get_submission(s) function to get all submissions)
        #                 submission = assignment.get_submission(user)
        #                 sub_path = os.path.join(assignment_folder, "my_submission.txt")
        #                 with open(sub_path, 'w', encoding='utf-8') as f:
        #                     f.write(f"Submitted at: {getattr(submission, 'submitted_at', 'Not submitted')}\n")
        #                     f.write(f"Grade: {getattr(submission, 'grade', 'Not graded')}\n")
        #                     f.write(f"Score: {getattr(submission, 'score', 'N/A')}\n\n")
            
        #                     # Submission comments (feedback)
        #                     if hasattr(submission, 'submission_comments'):
        #                         f.write("Comments:\n")
        #                         for comment in submission.submission_comments:
        #                             f.write(f"  - {comment.get('author_name', 'Unknown')}: {comment.get('comment', '')}\n")
                        
        #                     # Download submitted files
        #                     if hasattr(submission, 'attachments'):
        #                         for attachment in submission.attachments:
        #                             file_path = os.path.join(assignment_folder, attachment.filename)
        #                             response = requests.get(attachment.url)
        #                             with open(file_path, 'wb') as f:
        #                                 f.write(response.content)
        #                             print(f"Downloaded submission: {attachment.filename}")

        #                     # Text submissions case:
        #                     if hasattr(submission, 'body') and submission.body:
        #                         text_path = os.path.join(assignment_folder, "submission_text.html")
        #                         with open(text_path, 'w', encoding='utf-8') as f:
        #                             f.write(submission.body)
                            

        #                 print(f"Saved assignment in folder: {assignment_folder} in {module_course_download_path}")
        #                 break
        #             case 'Discussion':
        #                 discussion_id = item.content_id
        #                 discussion = course.get_discussion_topic(discussion_id)

        #                 file_name = sanitize_string(f"{discussion.title}.html")
        #                 file_path = os.path.join(module_course_download_path, file_name)

        #                 with open(file_path, 'w', encoding='utf-8') as f:
        #                     f.write(f"<h1>{discussion.title}</h1>")
        #                     f.write(f"<p>Posted: {getattr(discussion, 'posted_at', 'unknown')}</p>")
        #                     f.write(f"<div>{discussion.message if discussion.message else ""}</div>")
        #                     f.write(f"<h2>Discussion entries:<h2>")
        #                     try:
        #                         entries = discussion.get_topic_entries()
        #                         for entry in entries:
        #                             f.write(f"<div style='margin: 20px;'>")
        #                             f.write(f"<strong>{getattr(entry, 'user_name', 'Unknown')}</strong><br>")
        #                             f.write(f"{getattr(entry, 'message', '')}")
        #                             f.write(f"</div>")
        #                     except Exception as e:
        #                         f.write(f"<p>Could not load entries, error: {e}</p>")
                        
        #                 print(f"Saved Discussion as: {file_name} in {module_course_download_path}")
        #                 pass
        #                 break
        #             case 'ExternalUrl':
        #                 # Just going to save to a .txt file 
        #                 file_name = sanitize_string(f"{item.title}_link.txt")
        #                 file_path = os.path.join(module_course_download_path, file_name)
        #                 with open(file_path, 'w', encoding='utf-8') as f:
        #                     f.write(f"Title: {item.title}\n")
        #                     f.write(f"URL: {item.external_url}\n")
        #                 print(f"Saved external URL as: {file_name} in {module_course_download_path}")
        #                 pass
        #                 break
        #             case 'ExternalTool':
        #                 # note: this generated /Users/macbookpro/Projects/Canvas_webscraper/University_Engineering_Honours/Discrete_Mathematics_6698_Semester_2_2022_BRUCE_ON-CAMPUS_AND_Discrete_Mathematics_G_6699_Semester_2_2022_BRUCE_ON-CAMPUS/Pearson_Seamless_MyLab_Math/MyLab_Math_course_entry_external_tool.txt
        #                 # However I think the link is broken, so need to investigate further what this actually is
        #                 file_name = sanitize_string(f"{item.title}_external_tool.txt")
        #                 file_path = os.path.join(module_course_download_path, file_name)
        #                 with open(file_path, 'w', encoding='utf-8') as f:
        #                     f.write(f"Title: {item.title}\n")
        #                     f.write(f"URL: {item.external_url}\n")
        #                 print(f"Saved external URL as: {file_name} in {module_course_download_path}")
        #                 pass
        #                 break
        #             case 'SubHeader':
        #                 break
        #             case "Quiz":
        #                 break

        #             # This default case theoretically should never be hit...
        #             # supported types are listed on this page: https://canvas.instructure.com/doc/api/modules.html#method.context_module_items_api.create
        #             case _:
        #                 print("Unknown file type")
        #                 breakpoint()
        #         pass
        GotAssignmentFlag = 0    
        if GotAssignmentFlag == 0:
            assignments = course.get_assignments()
            for assignment in assignments:
                # assignment_id = item.content_id
                # assignment = course.get_assignment(assignment_id)
                assignment_download_path = f'{course_download_path}//ASSIGNMENTS'

                assignment_folder = os.path.join(assignment_download_path,
                                                    sanitize_string(assignment.name))
                
                make_directory(assignment_folder)

                # Save assignment description as html page (todo): look if there is a better format for this
                assignment_description_path = os.path.join(assignment_folder, "assignment_description.html")
                with open(assignment_description_path, 'w', encoding='utf-8') as f:
                    f.write(f"<h1>{assignment.name}</h1>")
                    f.write(f"<p>Due: {getattr(assignment, 'due_at', 'No due date')}</p>")
                    f.write(f"<p>Points: {getattr(assignment, 'points_possible', 'N/A')}</p>")
                    f.write(assignment.description if assignment.description else "")

                # Get submission(s): (todo):there is a get_submission(s) function to get all submissions)
                submission = assignment.get_submission(user)
                sub_path = os.path.join(assignment_folder, "my_submission.txt")
                with open(sub_path, 'w', encoding='utf-8') as f:
                    f.write(f"Submitted at: {getattr(submission, 'submitted_at', 'Not submitted')}\n")
                    f.write(f"Grade: {getattr(submission, 'grade', 'Not graded')}\n")
                    f.write(f"Score: {getattr(submission, 'score', 'N/A')}\n\n")
    
                    # Submission comments (feedback)
                    if hasattr(submission, 'submission_comments'):
                        f.write("Comments:\n")
                        for comment in submission.submission_comments:
                            f.write(f"  - {comment.get('author_name', 'Unknown')}: {comment.get('comment', '')}\n")
                
                    # Download submitted files
                    if hasattr(submission, 'attachments'):
                        for attachment in submission.attachments:
                            file_path = os.path.join(assignment_folder, attachment.filename)

                            ### Downloading the file (for large files we may need to handle partial downloads lolz)
                            # headers = {
                            #     'Range': f'bytes={start_bytes}-'
                            # }
                            # response = requests.get(url, headers=headers, stream=True)
                            # continue the above download process with streaming
                            try:
                                with requests.get(attachment.url, stream=True) as response:
                                    response.raise_for_status()
                                    with open(file_path, 'wb') as f:
                                        for chunk in response.iter_content(8192): 
                                            f.write(chunk)
                                print(f"Downloaded submission: {attachment.filename}")

                            except requests.exceptions.RequestException as e:
                                print("Error downloading the file:", e)

                            

                    # Text submissions case:
                    if hasattr(submission, 'body') and submission.body:
                        text_path = os.path.join(assignment_folder, "submission_text.html")
                        with open(text_path, 'w', encoding='utf-8') as f:
                            f.write(submission.body)
                    

                print(f"Saved assignment in folder: {assignment_folder} in {assignment_download_path}")

            
            pass
    pass