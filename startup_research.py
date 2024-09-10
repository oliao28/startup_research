import os.path
import io
from openai import OpenAI
from urllib.parse import urlparse, urlunparse
from gpt_researcher import GPTResearcher
import streamlit as st
import PyPDF2
from io import BytesIO
import pymupdf
import anthropic
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
    sourcelist = [url]
    print("start generating summary")
    prompt = "Give me a 5 sentence overview of the company at + " + url + " especially what products it offers and its end users, and the industry it operates in."
    researcher = GPTResearcher(prompt, report_type="custom_report", verbose = True, source_urls=sourcelist)
    research_result = await researcher.conduct_research()
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
    ],
     temperature = 0.2
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


#this function takes in a report and identifies the industry and sub-sector of a company
def identify_industry(report):
    
    industry = "Biotech"
    client = OpenAI()

    completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[
      {"role": "system", "content": "You are an expert in venture capital and assist non-experts in making assessments of specific technical fields."},
      {"role": "user", "content": "Using this report on a company: " + report + " please report back what the sub-sector industry is. This company is operating within the larger " + industry + " industry. Make sure that your response is more specific than the larger industry"},
      {"role": "assistant", "content": "Respond by using 1-3 words to decribe the field. Add nothing else. Be specific."}
    ]
    )
    
    response = str(completion.choices[0].message.content)

    return industry, response

async def industry_sector_report(industry, sector):
    report_type = "research_report"
    sources = ["https://www.taiwan-healthcare.org/zh/homepage", "https://www.ankecare.com/", "https://news.gbimonthly.com/", "https://technews.tw/"]

    prompt = """Please investigate the """+ industry + """industry and """ + sector + """sector. Create an instruction manual for investing in 
                this industry and this sector. Focus on what distinguishes venture capital investing in this industry and sector from others.
                Include a short summary of how the industry and sector are performing."""

    researcher = GPTResearcher(query=prompt, 
                                 report_type=report_type, source_urls=sources, report_source='static', verbose=True)
    research_result = await researcher.conduct_research()
    report = await researcher.write_report()

    return report

def expert_opinion(company, market):
    client = OpenAI()

    completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[
      {"role": "system", "content": "You are an expert in venture capital and assist non-experts in making assessments of specific technical fields."},
      {"role": "user", "content": "Using this report on a company: " + company + " and this report on the industry and sector of the company: " + market + " Please provide a 5 sentence analysis of the company's investment viability. Focus on the connections between the industry and sector analysis and the company. Do not focus on company data alone."},
      {"role": "assistant", "content": "You are an expert who sees the connections between large market trands and individual companies.."}
    ]
    )
    
    response = str(completion.choices[0].message.content)

    return response

#pulled from internet and works!
def is_encrypted(pdf_content):
    """Check if a PDF file is encrypted."""
    reader = PyPDF2.PdfReader(BytesIO(pdf_content))
    return reader.is_encrypted

async def decrypt_pdf(pdf_content, password):
    """Decrypt a password-protected PDF."""
    doc = pymupdf.open(stream=pdf_content.read(), filetype="pdf")
    
    # Check if the PDF is not encrypted
    if not doc.is_encrypted:
        return None, "The PDF file is not encrypted."

    if doc.authenticate(password):
        output_pdf = BytesIO()
        doc.save(output_pdf)
        output_pdf.seek(0)  # Reset the file pointer to the beginning
        await new_export_pdf(output_pdf) 
        return output_pdf, "PDF decrypted successfully!"
    else:
        return None, "Incorrect password! Unable to decrypt PDF."


async def conduct_research(session_state, research_config, uploaded_files):
    website = session_state.website
    try:
        # Use Anthropic Claude model. If it has outages, fall back to open AI
        if not session_state.company_description:
            session_state.company_description = await generate_summary(website)
        prompt = build_prompt(research_config["prompt"], st.session_state.website, st.session_state.company_description)
        online_report = await get_report("web", prompt, research_config["report_type"],
                                         research_config["agent"], research_config["role"], verbose=False)
    except anthropic.InternalServerError:
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["FAST_LLM_MODEL"] = "gpt-4o-mini"
        os.environ["SMART_LLM_MODEL"] = "gpt-4o"
        if not st.session_state.company_description:
            st.session_state.company_description = await generate_summary(website)
        prompt = build_prompt(research_config["prompt"], website, st.session_state.company_description)
        online_report = await get_report("web", prompt, research_config["report_type"],
                                         research_config["agent"], research_config["role"], verbose=False)

    online_report = check_point(online_report, website=website, summary=st.session_state.company_description)
    # code change making more
    if uploaded_files is not None:  # if document provided
        offline_report = await get_report("local", prompt, research_config["report_type"],
                                          research_config["agent"], research_config["role"], verbose=False)

        offline_report = check_point(offline_report, website=website, summary=st.session_state.company_description)

        report = combine_reports(research_config["prompt"], offline_report, online_report)
    else:
        report = online_report
    return report