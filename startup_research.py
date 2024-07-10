import asyncio
from gpt_researcher import GPTResearcher

from google.oauth2 import service_account
from googleapiclient.discovery import build
import gdown
import requests

import pymupdf

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

#This function takes in a link to a pitch deck and returns a tuple
#The first part of the tuple is all textual data from the pitch deck
#The second part of the tuple is all images from the pitch deck UNFINISHED
def parse_pitch_deck(link):
    #first get the pdf 
    try:
        r = requests.get(link)
        if r.status_code == 200:
            output = r"pitchdeck.pdf"
            gdown.download(link, output, fuzzy=True)
    except:
        pass

    #extract text
    doc = pymupdf.open("pitchdeck.pdf") # open a document
    for page in doc: # iterate the document pages
        text = page.get_text().encode("utf8") # get plain text (is in UTF-8)
        
    


    return text
