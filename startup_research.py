import asyncio
from gpt_researcher import GPTResearcher

async def get_report(prompt: str, report_type: str, agent=None,role=None,config_path = None, verbose = True) -> str:
    researcher = GPTResearcher(prompt, report_type, config_path = config_path, agent= agent, role=role, verbose = verbose)
    research_result = await researcher.conduct_research()
    report = await researcher.write_report()
    return report

def build_prompt(prompt: str, company_website: str, company_description: str):
    if company_description == '':
        return "Based on the website of this startup:" + company_website + ", first understand what it does. Then," + prompt
    else:
        return company_description + "\n" + "Here's it's website:" + company_website + "\n" + prompt

