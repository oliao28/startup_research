from currency_converter import CurrencyConverter
#-------------------------------------
# Variables for Peer Comparisons
#-------------------------------------
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
# Currency selection
c = CurrencyConverter()
all_currency =sorted(list(c.currencies))
frequent_currency = ['JPY', 'USD','EUR']
sorted_currency = sorted(all_currency, key=lambda x: frequent_currency.index(x) if x in frequent_currency else len(frequent_currency))

#-------------------------------------
# Variables for startup research
#-------------------------------------
prompt = """Write a short report containing the following sections, using simple bullet points whenever possible. 
Do NOT use markdown formatting. Remove any font formatting.
The title of the report is the company name. Only the listed sections are needed in the report, nothing else. Within each section, ask the investors to deep dive into critical questions that we do not yet know the answers of.
1. Website URL of the company on top
2. Team
 - Describe the founding team's academic and industry experience. Particularly answer why is the founding team uniquely qualified to solve this problem better than anyone else.
3. Market
 - Describe the reason why hasn’t this problem been solved before
 - Describe the competition landscape
 - Estimate the TAM size
 - What segment within the gigantic TAM are they focusing on first
 - what do we need to believe for their business to grow 100 times bigger?
4. Product
 - Describe the alternatives the customers are using today without their product
 - Describe the key selling points of the product
5. Traction
 - Describe the moat that would make their business hard to compete with or copy
 - Describe the growth in their customer counts, ARR or revenue
 - Describe the distribution channels the team used to find early customers
6. Exit strategy
7. Concerns
 - Describe reasons this startup might lose to competitors
 - Describe risks that would cause this startup to not grow
8. Deal structure
 - Describe how much they're raising and the valuation
 - Describe how the new fund will help accelerate growth
"""
reference_prompt = """
You MUST write all used source urls at the end of the report as references, and make sure to not add duplicated sources, but only one reference for each.
"""
prompt = prompt+"\n" + reference_prompt
research_config = {
	"llm_provider": "openai", #"anthropic",# 
	"fast_llm_model":  "gpt-4o-mini", #"claude-2.1",#
	"smart_llm_model": "gpt-4o", #"claude-3-5-sonnet-20240620", 
    "max_iterations": "6",
    "report_type": "custom_report",
    "agent": "venture capital agent",
	"prompt": prompt,
	"role": """You are an experienced AI venture capital analyst assistant. Your primary objective is to produce comprehensive,
            insightful, and impartial investment analyses based on provided company information, market trends, and competitive landscapes.
            If you don’t know the precise answers, ask the investors to deep dive into those questions.
    """
}
