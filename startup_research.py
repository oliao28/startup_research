import os.path
import pymupdf
import io
from openai import OpenAI
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from gpt_researcher import GPTResearcher

import streamlit as st

async def get_report(source: str, prompt: str, report_type: str, agent=None,role=None,config_path = None, verbose = True) -> str:
    researcher = GPTResearcher(prompt, report_type, report_source=source, config_path = config_path, agent= agent, role=role, verbose = verbose)
    research_result = await researcher.conduct_research()
    report = await researcher.write_report()
    return report

def build_prompt(prompt: str, company_website: str, company_description: str):
    return f"Based on the website of this startup: {company_website}, this summary of the company \'{company_description}\', and other available information about this company and its industry, first understand what it does. Then, {prompt}"


def get_company_name(report: str, company_website: str):
    name = report.split('\n')[0]
    name = name.replace("*", "").replace(" report", "")
    if len(name)<3 or len(name)>20:  # this is an arbitrary threshold assuming no one would name a company with more than 20 characters
      tmp = company_website.split('.')
      if "www" in tmp[0]:
          name = tmp[1]
      else:
          name = tmp[0]
    return name.capitalize()

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

async def new_generate_summary(link, sources):
  report_type = "custom_report"
  query = "Create a 5-sentence paragraph summarizing the with the following website: " + link + " following structure. Sentence 1: What industry does it operate in? Sentence 2: What does its’ industry or technical vertical seek to improve or sell Sentence 3: What products does the company sell? Sentence 4: What problem is this company trying to solve? Sentence 5: Who is the end-user of this company’ products?"

  researcher = GPTResearcher(query=query, report_type=report_type, source_urls=sources)
  await researcher.conduct_research()
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
    