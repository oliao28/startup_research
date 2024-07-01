import streamlit as st
import financial_analysis as fa
from config import all_metrics, sorted_currency, research_config
from startup_research import get_report, build_prompt
import os
import asyncio

os.environ["OPENAI_API_KEY"] =  st.secrets["open_api_key"] # Set the OpenAI API key as an environment variable
os.environ["TAVILY_API_KEY"] = st.secrets["tavily_api_key"] # Set the Tavyly API key as an environment variable
os.environ["ANTHROPIC_API_KEY"]= st.secrets["anthropic_api_key"]
os.environ["LLM_PROVIDER"]=research_config["llm_provider"]
os.environ["FAST_LLM_MODEL"]=research_config["fast_llm_model"]
os.environ["SMART_LLM_MODEL"]=research_config["smart_llm_model"]


async def main():
    tab_startup, tab_peer = st.tabs(["Startup Research", "Peer Comparison"])

    with tab_startup:
        st.header("Prepare a draft call memo and critical questions for due diligence")
        website = st.text_input('Enter company website URL')
        description = st.text_input('Describe the company in a few sentences (or leave blank if website is provided)')
        prompt = build_prompt(research_config["prompt"], website, description)

        if st.button("Prepare draft memo"):
            # # Create a placeholder for the log messages
            # log_output = st.empty()
            #
            # # Create a StringIO object to capture print output
            # f = io.StringIO()

            # # Redirect stdout to our StringIO object
            # with redirect_stdout(f):
            #     # Run get_report and capture its output
            report = await get_report(prompt, research_config["report_type"],
                        research_config["agent"], research_config["role"], verbose=False)

            # # Get the log output as a string
            # log_contents = f.getvalue()
            #
            # # Display the log messages
            # log_output.text(log_contents)

            # Display the final report
            st.subheader("Draft memo")
            st.write(report)

    with tab_peer:
        st.header('Peer Comparison Analysis')
        st.text(
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



