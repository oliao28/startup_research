import streamlit as st
import json
import financial_analysis as fa
from config import all_metrics, sorted_currency, research_config
from startup_research import *
import os
import re
import asyncio
import affinity_utils  as au
import anthropic

os.environ["OPENAI_API_KEY"] =  st.secrets["openai_api_key"] # Set the OpenAI API key as an environment variable
os.environ["TAVILY_API_KEY"] = st.secrets["tavily_api_key"] # Set the Tavyly API key as an environment variable
os.environ["ANTHROPIC_API_KEY"]= st.secrets["anthropic_api_key"]
os.environ["LLM_PROVIDER"]=research_config["llm_provider"]
os.environ["FAST_LLM_MODEL"]=research_config["fast_llm_model"]
os.environ["SMART_LLM_MODEL"]=research_config["smart_llm_model"]
os.environ["MAX_ITERATIONS"]=research_config["max_iterations"]
os.environ["DOC_PATH"] = os.path.join("company")

AFFINITY_API_KEY = st.secrets["affinity_api_key"]

GOOGLE_CRED = json.loads(str(st.secrets["GOOGLE_CRED"]))
GOOGLE_TOKEN = json.loads(str(st.secrets["GOOGLE_TOKEN"]))



# Function to write credentials to JSON files
#By writing locally, it allows for the potential to update the credentials
def write_credentials_to_files():
    with open('credentials.json', 'w') as cred_file:
        json.dump(GOOGLE_CRED, cred_file, indent=4)

    with open('token.json', 'w') as token_file:
        json.dump(GOOGLE_TOKEN, token_file, indent=4)


async def main():
    tab_startup, tab_peer = st.tabs(["Startup Research", "Peer Comparison"])
    # Initialize session state variables
    if 'report' not in st.session_state:
        st.session_state.report = None

    with tab_startup:
        st.header("Research a startup and draft the call memo")
        st.markdown(
            """Use this app to conduct preliminary research on a startup based on its website and public information.
               The app will draft a call memo and recommend critical questions to ask during due diligence.
               You can add the startup and memo directly to Affinity or copy and paste the draft into your favorite note-taking app. 
               Check out the full introduction [here.](https://docs.google.com/document/d/1vlrP3R-BN_hMecRINpNS4y8ZVQ1EnpLABahc10u0Cy8/edit?usp=sharing)         
            """ )
        website = st.text_input('Enter company website URL')
        description = st.text_input('Describe the company in a few sentences (or leave blank if website is provided)')
        prompt = build_prompt(research_config["prompt"], website, description)

        #first get a link to a pitchdeck
        uploaded_files = st.file_uploader("Upload any documents you have from the company.")
        if st.button("Draft call memo"):
            if not website:
                st.warning("Please add a link to a website to enable drafting the call memo.", icon="🚨")
            else:
                if not description: #if there is no description
                    sources = [website]
                    description = await new_generate_summary(website, sources)

                online_report = await get_report("web", prompt, research_config["report_type"],
                                                research_config["agent"], research_config["role"], verbose=False)

                online_report = check_point(online_report, website=website, summary=description)

                if uploaded_files is not None: #if link to pitchdeck is not empty
                    await new_export_pdf(uploaded_files)
                    offline_report = await get_report("local", prompt, research_config["report_type"],
                            research_config["agent"], research_config["role"], verbose=False)

                    offline_report = check_point(offline_report, website=website, summary=description)

                    report = combine_reports(research_config["prompt"], offline_report, online_report)
                else:
                    report = online_report

                # Store the report in session state
                st.session_state.report = report
            # Display the report if it exists in session state
            if st.session_state.report:
                st.write("Company Description")
                st.write(description)
                st.write(st.session_state.report)
                # Add to Affinity
                if st.button("Add to Affinity"):
                    # Replace LIST_ID with the actual ID of your Affinity list
                    list_id = '143881'
                    company_name = get_company_name(st.session_state.report, website)

                    company_data = {
                        "name": company_name,
                        "domain": website,
                    }
                    org_result = au.create_organization_in_affinity(AFFINITY_API_KEY, company_data)
                    if org_result:
                        st.success(f"Created organization ID: {org_result['id']}", icon="✅")
                        # Now, add the organization to the list
                        au.add_entry_to_list(AFFINITY_API_KEY, list_id, org_result['id'])

                        # Now add notes to the organization
                        note_result = au.add_notes_to_company(AFFINITY_API_KEY, org_result['id'], st.session_state.report)
                        if note_result:
                            st.success(f"Added note to: {company_name}", icon="✅")
                    # else:
                    #     st.error("Failed to create organization")
    with tab_peer:
        st.header('Peer Comparison Analysis')
        st.markdown(
            'For a list of public companies, compare selected financial metrics from their annual report (sourced from Yahoo Finance)')
        # Input for companies
        companies_input = st.text_input('Enter company names (comma-separated)', 'Apple, Microsoft, Google')
        companies = [company.strip() for company in companies_input.split(',')]
        selected_metrics = st.multiselect('Select metrics', all_metrics, default=["Revenue", "Valuation", "P/S ratio"])
        target_currency = st.selectbox('Select target currency', sorted_currency)
        year = st.text_input('Enter year (YYYY) or leave empty for most recent TTM', None)

        if st.button('Analyze'):
            with st.spinner('Analyzing companies...'):
                results_df = fa.analyze_multiple_companies(companies, selected_metrics, target_currency, year)
                formatted_df = fa.format_dataframe(results_df)

            st.write(formatted_df)

            # Download button for CSV
            csv = results_df.to_csv(index=True)
            st.download_button(
                label="Download data as CSV",
                data=csv,
                file_name="financial_analysis.csv",
                mime="text/csv",
            )

if __name__ == "__main__":
    asyncio.run(main())



