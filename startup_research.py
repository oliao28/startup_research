import os.path
# import pymupdf
import io
from openai import OpenAI
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from urllib.parse import urlparse, urlunparse

from gpt_researcher import GPTResearcher

import streamlit as st

async def get_report(source: str, prompt: str, report_type: str, agent=None,role=None,config_path = None, verbose = True) -> str:
    researcher = GPTResearcher(prompt, report_type, report_source=source, config_path = config_path, agent= agent, role=role, verbose = verbose)
    research_result = await researcher.conduct_research()
    report = await researcher.write_report()
    return report

def build_prompt(prompt: str, company_website: str, company_description: str):
    return f"Based on the website of this startup: {company_website}, this summary of the company \'{company_description}\', and other available information about this company and its industry, first understand what it does. Then, {prompt}"


#this function integrates the two reports, online and offline
def combine_reports(prompt, offline, online):
    client = OpenAI()

    completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[
      {"role": "system", "content": "You are a helpful assistant that can integrate two reports into a single one. You do not do research of your own. You only copy and paste statements from each report and reformat. Do not use any special fonts, italics, or font colors. You many only bold the section headers and underline the reference links."},
      {"role": "user", "content": "Please integrate these two reports. The first report is done on offline research: " + offline + " The second report is done by online research: " + online + "use the format of " + prompt},
      {"role": "assistant", "content": "Stick to the same format as the reports. There are eight sections: Website, Team, Market, Product, Traction, Exit Strategy, Concerns, and Deal Structure. Each section begins with factual statements regarding the section topic. If a factual statement comes from the offline research, please cite it by attaching \"Pitchdeck\" to the end of the statement. If a factual statement comes from online research, please cite it by attaching \"Online\" to the end of the statement. When factual statements from the offline and online reports conflict and disagree, rewrite the statement using this formar \'Online research says that [INSERT THE FACTUAL STATEMENT FROM ONLINE RESEARCH] but offline research says [INSERT THE FACTUAL STATEMENT FROM OFFLINE RESEARCH]\' the append \"CONFLICT\" to the end of the statement. Each factual statement subsection then followed by a subsection titled \"investor questions\" All questions should go into that subsection. If one of the questions is answered by the factual statements included before, do not include that question. If the questions repeat each other, only include the question once"}
    ]
    )

    response = str(completion.choices[0].message.content)
    return response

def extract_text_from_elements(elements):
    return " ".join([element.text for element in elements if element.text.strip()])

def validate_url(url):
    parsed = urlparse(url)
    if not parsed.scheme:
        return urlunparse(('https', *parsed[1:]))
    return url

async def generate_summary(url):
    sourcelist =[url]
    print(sourcelist)
    print(url)
    print("start generating summary")
    prompt = f"Give me a 5 sentence overview of the company at + " + url + " especially what products it offers and its end users, and the industry it operates in."
    researcher = GPTResearcher(prompt, report_type="custom_report", verbose = True, source_urls=sourcelist)
    research_result = await researcher.conduct_research()
    print(research_result)
    report = await researcher.write_report()
    return report

#this is the checkpoint function, it takes in a report, website, and company description
#it then uses GPT to do online research and check the validity of any claims. 
#It seeks to correct the information and outputs the corrected report
#it is called after each report it made. If no description exists, it makes the description.
def check_point(report, website, summary):
    client = OpenAI()

    completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[
      {"role": "system", "content": "You are a helpful assistant that fact checks reports. In addition to fact-checking, you also modify fonts, colors, and text to standardize formats"},
      {"role": "user", "content": "Using this website: " + website + " and this company description: \'" + summary + "\' First understand what the company does. Then, going one bullet point at a time, fact check the following report \'" + report + "\' If a claim is accurate, make no modifications or additions to the report. Do not add a new line or mark the line in any way or form. If the claim is inaccurate, modify the line with the correct information."},
      {"role": "assistant", "content": "Stick to the same format as the report. If a claim is accurate, make no modifications. Only modify when a claim is inaccurate. There are eight sections: Website, Team, Market, Product, Traction, Exit Strategy, Concerns, and Deal Structure. Each section begins with factual statements regarding the section topic and is followed by a Questions section. Do not modify the Questions section."}
    ]
    )

    response = str(completion.choices[0].message.content)
    return response


#this downloads the file
async def new_export_pdf(uploaded_file):
  # Save the file
  file_path = os.path.join("company", "pitchdeck.pdf")
  os.makedirs("company", exist_ok=True)

  with open(file_path, "wb") as f:
    f.write(uploaded_file.getbuffer())

#This function takes in a real_file_id and downloads the pdf to "pitchdeck.pdf"
#there is no return value
#This function is called by app.py and reutrns to the main flow
SCOPES = ["https://www.googleapis.com/auth/drive"]
async def export_pdf(real_file_id):
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

    # Download the file to Streamlit temp folder
    # Note: this could be a security risk we need to fix
    request = service.files().get_media(fileId=real_file_id)
    file_path = os.path.join("company", "pitchdeck.pdf")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with io.FileIO(file_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%.")

  except HttpError as error:
    print(f"An error occurred: {error}")
    file = None

def dynamic_prompting():
   #find the industry

   #point at repo for industry

   return None

def user_inquiry():
   #take in user request:

   #provided information: reports, pitchdeck, website, company decription, and expert opinion
   return None
