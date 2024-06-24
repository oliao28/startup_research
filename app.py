import streamlit as st
import financial_analysis as fa
from currency_converter import CurrencyConverter
st.title('Peer Comparison Analysis')

# Input for companies
companies_input = st.text_input('Enter company names (comma-separated)', 'Apple, Microsoft, Google')
companies = [company.strip() for company in companies_input.split(',')]
#companies_input = st.text_input('Enter year (default to latest TTM)', 2023)

# Multi-select for metrics
all_metrics = [
    "Revenue",
    "Cost of revenue",
    "Net income",
    "Valuation",
    'Employees',
    'Gross margin',
    "P/S ratio",
    "P/E ratio",
]
selected_metrics = st.multiselect('Select metrics', all_metrics, default=["Revenue", "Valuation", "P/S ratio"])

# Currency selection
c = CurrencyConverter()
all_currency =sorted(list(c.currencies))
frequent_currency = ['JPY', 'USD','EUR']
sorted_currency = sorted(all_currency, key=lambda x: frequent_currency.index(x) if x in frequent_currency else len(frequent_currency))
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