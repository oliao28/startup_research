import os.path
import pymupdf
import io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from gpt_researcher import GPTResearcher

async def get_report(prompt: str, report_type: str, agent=None,role=None,config_path = None, verbose = True) -> str:
    researcher = GPTResearcher(prompt, report_type, config_path = config_path, agent= agent, role=role, verbose = verbose)
    research_result = await researcher.conduct_research()
    report = await researcher.write_report()
    return report

def build_prompt(prompt: str, company_website: str, company_description: str, pitch_deck: str):
    if company_description == '':
        return "Based on the website of this startup:" + company_website + " and the pitch deck Text: " + pitch_deck + ", first understand what it does. Then," + prompt 
    else:
        return company_description + "\n" + " and here is the pitch deck Text: " + pitch_deck + " Here's it's website:" + company_website + "\n" + prompt

def get_company_name(report: str, company_website: str):
    name = report.split('\n')[0]
    if len(name)<3 or len(name)>20:  # this is an arbitrary threshold assuming no one would name a company with more than 20 characters
      tmp = company_website.split('.')
      if "www" in tmp[0]:
          name = tmp[1]
      else:
          name = tmp[0]
    return name.capitalize()


#This function takes in a real_file_id and downloads the pdf to "pitchdeck.pdf"
#there is no return value
#This function is called by app.py and reutrns to the main flow
SCOPES = ["https://www.googleapis.com/auth/drive"]
def export_pdf(real_file_id):
  """Download a Document file in PDF format.
  Args:
      real_file_id : file ID of any workspace document format file
  Returns : IO object with location

  Load pre-authorized user credentials from the environment.
  TODO(developer) - See https://developers.google.com/identity
  for guides on implementing OAuth2 for the application.
  """

  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "credentials.json", SCOPES
      )
      creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
      token.write(creds.to_json())

  try:
    service = build("drive", "v3", credentials=creds)

    # Download the file
    request = service.files().get_media(fileId=file_id)
    with io.FileIO("pitchdeck.pdf", 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%.")

  except HttpError as error:
    print(f"An error occurred: {error}")
    file = None
 
def parse_pitch_deck():
    #extract text
    doc = pymupdf.open("pitchdeck.pdf") # open a document
    text = ""
    for page in doc: # iterate the document pages
        text += page.get_text() # get plain text 
    return text
