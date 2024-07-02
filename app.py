import streamlit as st
import financial_analysis as fa
from config import all_metrics, sorted_currency, research_config
from startup_research import get_report, build_prompt, get_company_name
import os
import asyncio
import affinity_utils  as au
from dotenv import load_dotenv
# load_dotenv()  # take environment variables from .env.
# open_api_key = os.getenv("OPENAI_API_KEY")
# tavily_api_key = os.getenv("TAVILY_API_KEY")
# anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
# AFFINITY_API_KEY = os.getenv('AFFINITY_API_KEY')
os.environ["OPENAI_API_KEY"] =  st.secrets["openai_api_key"] # Set the OpenAI API key as an environment variable
os.environ["TAVILY_API_KEY"] = st.secrets["tavily_api_key"] # Set the Tavyly API key as an environment variable
os.environ["ANTHROPIC_API_KEY"]= st.secrets["anthropic_api_key"]
os.environ["LLM_PROVIDER"]=research_config["llm_provider"]
os.environ["FAST_LLM_MODEL"]=research_config["fast_llm_model"]
os.environ["SMART_LLM_MODEL"]=research_config["smart_llm_model"]
AFFINITY_API_KEY = st.secrets["affinity_api_key"]


async def main():
    tab_startup, tab_peer = st.tabs(["Startup Research", "Peer Comparison"])
    # Initialize session state variables
    if 'report' not in st.session_state:
        st.session_state.report = None

    with tab_startup:
        st.header("Research a startup and draft the call memo")
        st.markdown(
            """Use this app to get a preliminary research of a startup based on its 
            website and public information. The app will draft a call memo and recommend
            critical questions you should ask during due diligence. Add the startup and memo directly
            to Affinity or copy paste the draft into your favorite notes talking app.            
            """)
        website = st.text_input('Enter company website URL')
        description = st.text_input('Describe the company in a few sentences (or leave blank if website is provided)')
        prompt = build_prompt(research_config["prompt"], website, description)

        if st.button("Draft call memo"):
            report = await get_report(prompt, research_config["report_type"],
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
                    au.add_notes_to_company(AFFINITY_API_KEY, org_result['id'], st.session_state.report)
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



