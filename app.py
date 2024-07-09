import streamlit as st
from config import all_metrics, sorted_currency, research_config
from googleapiclient.discovery import build
import os
import asyncio
import affinity_utils  as au
import threading
from datetime import datetime
import financial_analysis as fa
import startup_research as sr
import gdrive_qna as gq

os.environ["OPENAI_API_KEY"] =  st.secrets["openai_api_key"] # Set the OpenAI API key as an environment variable
os.environ["TAVILY_API_KEY"] = st.secrets["tavily_api_key"] # Set the Tavyly API key as an environment variable
os.environ["ANTHROPIC_API_KEY"]= st.secrets["anthropic_api_key"]
os.environ["LLM_PROVIDER"]=research_config["llm_provider"]
os.environ["FAST_LLM_MODEL"]=research_config["fast_llm_model"]
os.environ["SMART_LLM_MODEL"]=research_config["smart_llm_model"]
AFFINITY_API_KEY = st.secrets["affinity_api_key"]

#TODO: During the update of pinecone, remove repetitie information from repeated insert
#TODO: figure out how to set namespace
async def main():
    tab_startup, tab_peer, tab_qna = st.tabs(["Startup Research", "Peer Comparison", "Darwin Knowledge Q&A"])
    # Initialize session state variables
    if 'report' not in st.session_state:
        st.session_state.report = None
    # Updated whenever the user asks a question.
    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = datetime.now()

    with tab_startup:
        st.header("Research a startup and draft the call memo")
        st.markdown(
            """Use this app to conduct preliminary research on a startup based on its website and public information. 
            The app will draft a call memo and recommend critical questions to ask during due diligence. 
            You can add the startup and memo directly to Affinity or copy and paste the draft into your favorite note-taking app.     
            """)
        website = st.text_input('Enter company website URL')
        description = st.text_input('Describe the company in a few sentences (or leave blank if website is provided)')
        prompt = sr.build_prompt(research_config["prompt"], website, description)

        if st.button("Draft call memo"):
            report = await sr.get_report(prompt, research_config["report_type"],
                        research_config["agent"], research_config["role"], verbose=False)
            # Store the report in session state
            st.session_state.report = report
        # Display the report if it exists in session state
        if st.session_state.report:
            # st.subheader("Draft memo")
            st.write(st.session_state.report)
            # Add to Affinity
            if st.button("Add to Affinity"):
                # Replace LIST_ID with the actual ID of your Affinity list
                list_id = '143881'
                company_name = sr.get_company_name(st.session_state.report, website)
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
    with tab_qna:
        st.header('Darwin Knowledge Q&A')
        st.markdown(
            'Ask questions and get answers from Darwin\'s Google drive' )
        # Initialize session state
        if 'credentials' not in st.session_state:
            credentials_path = 'desk_credentials.json'  # TODO: Update this path
            st.session_state.credentials = gq.authenticate_google_drive(credentials_path)

        if 'folder_id' not in st.session_state:
            st.session_state.folder_id = '1JHdl4fsFJoysaByHMS1SCh7KO_EBqaS1'  #TODO: Replace with your actual folder ID

        if 'last_update_file_id' not in st.session_state:
            drive_service = build('drive', 'v3', credentials=st.session_state.credentials)
            st.session_state.last_update_file_id = gq.get_or_create_last_update_file(drive_service,
                                                                                  st.session_state.folder_id)
        #check_and_update_index runs every 10 mins.  It checks if the user has been inactive for more than 10 minutes,
        # and if so, it checks if it's been more than a week since the last update. If both conditions are met, it triggers an update.
        # Check and update index
        gq.check_and_update_index(drive_service)

        # Q&A Interface
        user_question = st.text_input("Enter your question:")
        if st.button("Ask"):
            if user_question:
                st.session_state.last_activity = datetime.now()
                query_engine = gq.get_query_engine()
                response = query_engine.query(user_question)

                st.write("Answer:", response.response)
                st.write("Sources:")
                for source_node in response.source_nodes:
                    file_id = source_node.node.metadata.get('file id')
                    file_name = source_node.node.metadata.get('file name')
                    if file_id:
                        file_url = gq.get_file_url(file_id)
                        st.write(f"- [{file_name}]({file_url})")
if __name__ == "__main__":
    asyncio.run(main())

