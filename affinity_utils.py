import base64
import requests

url_affinity_organizations = "https://api.affinity.co/organizations"
url_affinity_note = "https://api.affinity.co/notes"
url_affinity_persons = "https://api.affinity.co/persons"
url_affinity_field_values = "https://api.affinity.co/field-values"
url_affinity_list = "https://api.affinity.co/lists"
deal_list_id = '143881'
def affinity_authorization(affinity_api_key):
    username = ""
    pwd = affinity_api_key
    auth = "Basic " + base64.b64encode(f"{username}:{pwd}".encode()).decode()
    headers = {"Authorization": auth,
               "Content-Type": "application/json",
               "User-Agent": "startupresearch"}
    return headers


def get_company_name(report: str, company_website: str):
    name = report.split('\n')[0]
    name = name.replace("*", "").replace(" report", "")
    if len(name)<3 or len(name)>20:  # this is an arbitrary threshold assuming no one would name a company with more than 20 characters
      tmp = company_website.split('.')
      if "www" in tmp[0]:
          name = tmp[1]
      else:
          name = tmp[0]
    return name.capitalize()

def create_organization_in_affinity(affinity_api_key, organization_data):
    """
    return
        whether the org already exists in Affinity,
        org details
    """
    # Create headers with authentication
    headers = affinity_authorization(affinity_api_key)

    # First, search for the organization
    search_params = {"term": organization_data.get("domain", "")}
    search_response = requests.get(url_affinity_organizations, headers=headers, params=search_params)

    if search_response.status_code == 200:
        search_results = search_response.json()
        if search_results["organizations"]:
            # Organization already exists
            return search_results["organizations"][0]

    # Make the POST request
    company_name = get_company_name(organization_data.get("report"),organization_data.get("domain"))
    response = requests.post(url_affinity_organizations,
                             json={"name": company_name, "domain": organization_data["domain"]}, headers=headers)

    # Check if the request was successful
    if response.status_code in [200, 201]:
        return response.json()  #response will contains entity_id of the new organization
    else:
        return None

def find_dict_by_entity_id(dict_list, target_id):
    for dictionary in dict_list:
        if dictionary.get("entity_id") == target_id:
            return dictionary
    return None
def add_entry_to_list(affinity_api_key, list_id, entity_id):# list_id is 143881
    headers = affinity_authorization(affinity_api_key)
    full_url = f"{url_affinity_list}/{list_id}/list-entries"
    # First, check if the organization is already in the list
    check_response = requests.get(full_url, headers=headers)
    if check_response.status_code == 200:
        existing_entries = check_response.json()
        output = find_dict_by_entity_id(existing_entries, entity_id)
        if output:
            return output
        else:
            # if the entry doesnt' exist, either because check_response is 404 or the return list is >1, Make the POST request
            response = requests.post(full_url, json={"entity_id": entity_id}, headers=headers)
            # Check if the request was successful
            if response.status_code in [200, 201]:
                print("Organization added to list successfully!")
                return response.json()
            else:
                print(f"Failed to add organization to list. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                return None
    else:
        print("this Affinity list doesn't exist!")


def add_notes_to_company(affinity_api_key, organization_id, note):
    headers = affinity_authorization(affinity_api_key)
    note_data = {"organization_ids": [organization_id], "content": note}
    response = requests.post(url_affinity_note, headers=headers, json=note_data)
    # if response.status_code == 201:
    if response.status_code in [200, 201]:
        print("Notes added to the company successfully! Status code: {response.status_code}")
        return response.json()
    else:
        print(f"Failed to add notes to the company. Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return None
#
# async def get_startup_by_name(affinity_api_key, owner_value, startup_name):
#     subnames = startup_name.split()
#     search_term = "+".join(subnames)
#     headers = affinity_authorization(affinity_api_key)
#     next_page_token = None
#
#     while True:
#         full_url = f"{url_affinity_organizations}?term={search_term}&with_interaction_dates=true&with_interaction_persons=true"
#         if next_page_token:
#             full_url += f"&page_token={next_page_token}"
#
#         r = requests.get(full_url, headers=headers)
#         r.raise_for_status()
#         response = r.json()
#
#         for organization in response["organizations"]:
#             if organization.get("interactions"):
#                 for interaction_data in organization["interactions"].values():
#                     if interaction_data:
#                         people_involved = str(interaction_data["person_ids"])
#                         if owner_value in people_involved:
#                             return organization
#
#         next_page_token = response.get("next_page_token")
#         if not next_page_token:
#             return None
#
# async def get_field_values(affinity_api_key, type_id, id):
#     full_url = f"{url_affinity_field_values}?{type_id}={id}"
#     headers = affinity_authorization(affinity_api_key)
#     r = requests.get(full_url, headers=headers)
#     r.raise_for_status()
#     return r.json()
#
#
# async def add_field_value(affinity_api_key, field_id, entity_id, value, list_entry_id):
#     headers = affinity_authorization(affinity_api_key)
#     full_url = url_affinity_field_values
#     data = {
#         "field_id": field_id,
#         "entity_id": entity_id,
#         "value": value,
#         "list_entry_id": list_entry_id,
#     }
#     try:
#         r = requests.post(full_url, headers=headers, json=data)
#         r.raise_for_status()
#         print(r.json())
#         return "Success"
#     except requests.exceptions.RequestException as e:
#         print(f"Error: {e}")
#         return None
#
# def extract_title_and_note(text):
#     import re
#     pattern = r'^# .*\n'
#     matches = re.findall(pattern, text, re.MULTILINE)
#     title = matches[0] if matches else ""
#     substrings = re.split(pattern, text, flags=re.MULTILINE)
#     print(f"Title: {title}")
#     print(substrings)
#     return [title, substrings]
#
# def format_number(number):
#     abbreviations = {
#         'T': 1000000000000,
#         'B': 1000000000,
#         'M': 1000000,
#         'K': 1000,
#     }
#     for abbreviation, value in abbreviations.items():
#         if number >= value:
#             rounded_number = math.ceil(number / value)
#             return f"{rounded_number}{abbreviation}"
#     return str(number)