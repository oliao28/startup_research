from yahooquery import Ticker, search
import pandas as pd
import os
from currency_converter import CurrencyConverter

def get_symbol(company_name):
    results = search(company_name.capitalize())
    if results:
        return results['quotes'][0]['symbol']
    return None


def analyze_financial_data(company: str, metrics: list, target_currency: str = 'USD', year: int = None) -> dict:
    """
    Analyze financial data for a given company and return specified metrics.

    :param company: Name of the company to analyze
    :param metrics: List of metrics to retrieve
    :param year: Year to retrieve financial data for (default: current year)
    :param target_currency: Currency to convert financial values to (default: USD)
    :return: Dictionary with the requested financial information
    """

    symbol = get_symbol(company)
    if not symbol:
        return {metric: f"No symbol found for {company}" for metric in metrics}

    ticker = Ticker(symbol)

    # Fetch all potentially needed data
    income_statement = pd.DataFrame(ticker.income_statement())
    if year is None:  # use the latest available numbers
        income_statement = income_statement[income_statement['TotalRevenue'].notna()].sort_values('asOfDate',
                                                                                                  ascending=False)
    else:  # use the highest number of that year
        income_statement = income_statement[income_statement['asOfDate'].dt.year == year].sort_values('TotalRevenue',
                                                                                                      ascending=True)
    statistics = pd.DataFrame(ticker.summary_detail).T
    key_stats = ticker.key_stats
    profile = ticker.asset_profile
    # balance_sheet = pd.DataFrame(ticker.balance_sheet())
    # cash_flow = pd.DataFrame(ticker.cash_flow())

    # Get the company's reporting currency
    if not income_statement.empty and 'currencyCode' in income_statement.columns:
        company_currency = income_statement['currencyCode'].iloc[0]
    else:
        company_currency = 'USD'
        # Initialize currency converter
    # c = CurrencyRates()
    c = CurrencyConverter()

    def convert_currency(value, from_currency, to_currency):
        if from_currency == to_currency:
            return value
        try:
            # rate = c.get_rate(from_currency, to_currency)
            # return value * rate
            return c.convert(value, from_currency, to_currency)
        except:
            return value  # Return original value if conversion fails

    results = {}
    for metric in metrics:
        # metric = metric.lower()
        ## money metrics
        if 'Revenue' in metric:
            if not income_statement.empty and 'TotalRevenue' in income_statement.columns:
                value = income_statement['TotalRevenue'].iloc[0]
                results[metric] = convert_currency(value, company_currency, target_currency)
            else:
                results[metric] = "N/A"

        elif 'Cost of revenue' in metric:
            if not income_statement.empty and 'CostOfRevenue' in income_statement.columns:
                value = income_statement['CostOfRevenue'].iloc[0]
                results[metric] = convert_currency(value, company_currency, target_currency)
            else:
                results[metric] = "N/A"

        elif 'Net income' in metric:
            if not income_statement.empty and 'NetIncome' in income_statement.columns:
                value = income_statement['NetIncome'].iloc[0]
                results[metric] = convert_currency(value, company_currency, target_currency)
            else:
                results[metric] = "N/A"

        elif 'Valuation' in metric:
            if 'marketCap' in statistics.columns:
                value = statistics['marketCap'].iloc[0]
                report_currency = statistics['currency'].iloc[0]
                results[metric] = convert_currency(value, report_currency, target_currency)
            else:
                results[metric] = "N/A"
        elif 'Cash flow' in metric:
            if not cash_flow.empty and 'CashFlowFromOperatingActivities' in cash_flow.columns:
                value = cash_flow['CashFlowFromOperatingActivities'].iloc[-1]
                results[metric] = convert_currency(value, company_currency, target_currency)
            else:
                results[metric] = "N/A"
        ## non-money metrics
        elif 'Employees' in metric:
            if 'fullTimeEmployees' in profile[symbol]:
                results[metric] = profile[symbol]['fullTimeEmployees']
            else:
                results[metric] = "N/A"

        elif 'Gross margin' in metric:  # This is calculated as (Revenue - Cost of Revenue) / Revenue * 100.
            if not income_statement.empty and 'TotalRevenue' in income_statement.columns and 'CostOfRevenue' in income_statement.columns:
                revenue = income_statement['TotalRevenue'].iloc[0]
                cost_of_revenue = income_statement['CostOfRevenue'].iloc[0]
                if revenue != 0:
                    gross_margin = (revenue - cost_of_revenue) / revenue * 100
                    results[metric] = gross_margin
                else:
                    results[metric] = "N/A"
            else:
                results[metric] = "N/A"
        elif 'P/S ratio' in metric:
            if not statistics.empty and 'priceToSalesTrailing12Months' in statistics.columns:
                results[metric] = statistics['priceToSalesTrailing12Months'].iloc[0]
            else:
                results[metric] = "N/A"

        elif 'P/E ratio' in metric:
            if not statistics.empty and 'trailingPE' in statistics.columns:
                results[metric] = statistics['trailingPE'].iloc[0]
            else:
                results[metric] = "N/A"
        else:
            results[metric] = f"Metric '{metric}' not found or not implemented"

    return results


def analyze_multiple_companies(companies: list, metrics: list, target_currency: str = 'USD',
                               year: str = None) -> pd.DataFrame:
    """
    Analyze financial data for multiple companies and return results in a DataFrame.

    :param companies: List of company names to analyze
    :param metrics: List of metrics to retrieve for each company
    :return: DataFrame with metrics as rows and companies as columns
    """
    results = {}
    if year is not None:
        year = int(year)
    for company in companies:
        company_data = analyze_financial_data(company, metrics, target_currency, year)
        results[company] = company_data

    df = pd.DataFrame(results)
    return df


def format_dataframe(df):
    def format_value(value, metric):
        if isinstance(value, (int, float)):
            if metric.lower() in ['revenue', 'cost of revenue', 'valuation', 'net income']:
                if abs(value) >= 1e9:
                    return f" {value / 1e9:.2f}B"
                elif abs(value) >= 1e6:
                    return f"{value / 1e6:.2f}M"
                elif abs(value) >= 1e3:
                    return f"{value / 1e3:.2f}K"
                else:
                    return f"{value:.2f}"
            elif 'ratio' in metric.lower():
                return f"{value:.2f}"
            elif 'employees' in metric.lower():
                return f"{value:,.0f}"
            elif 'margin' in metric.lower():
                return f"{value:.2f}%"
            else:
                return f"{value:,.2f}"
        return value

    formatted_df = df.copy()
    for index, row in formatted_df.iterrows():
        formatted_df.loc[index] = row.apply(lambda x: format_value(x, index))

    return formatted_df