import os
import logging
import streamlit as st
from pinecone import Pinecone, ServerlessSpec
# from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
# from llama_index.readers.google import GoogleDriveReader
from llama_index.vector_stores.pinecone import PineconeVectorStore
# import time
# from datetime import datetime, timedelta
# from googleapiclient.http import MediaIoBaseUpload
# import io
from llama_index.llms.anthropic import Anthropic
from config import qna_system_prompt
os.environ["PINECONE_API_KEY"]=st.secrets["pinecone_api_key"]
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def authenticate_google_drive(credentials_path): #TODO: need to make it work with Streamlit cloud. Try running quickstart.py
    creds = None
    if os.path.exists('token.json'):
        logging.info("Automatically authentication")
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            logging.info("Initialize an authentication")
            flow = InstalledAppFlow.from_client_secrets_file(
                "web_credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=8001, prompt='consent')
            # flow = Flow.from_client_secrets_file(
            #     credentials_path,
            #     scopes=SCOPES,
            #     redirect_uri='http://127.0.0.1:9004')
            #
            # auth_url, _ = flow.authorization_url(prompt='consent')
            #
            # print(f"Please visit this URL to authorize the application: {auth_url}")
            # code = input("Enter the authorization code: ")
            # flow.fetch_token(code=code)
            # creds = flow.credentials

        with open('token.json', 'w') as token:
            logging.info("Create token file")
            token.write(creds.to_json())

    return creds


# Set up Pinecone
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index_name = "googledrive-qa"
pinecone_index = pc.Index(index_name)

# Global variables
index = None
query_engine = None

@st.cache_resource
def get_query_engine():
    global index, query_engine
    if index is None:
        logging.info("Initialize index")
        vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_documents([], storage_context=storage_context)
    if query_engine is None:
        logging.info("Create query engine")
        llm = Anthropic(model="claude-3-5-sonnet-20240620", system_prompt=qna_system_prompt)
        query_engine = index.as_query_engine(llm=llm)
    return query_engine


def get_file_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"
