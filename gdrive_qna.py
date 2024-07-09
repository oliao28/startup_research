import os
import logging
import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from llama_index import VectorStoreIndex, SimpleDirectoryReader, Document
from llama_index.readers import GoogleDriveReader
from llama_index.storage.storage_context import StorageContext
from llama_index.vector_stores import PineconeVectorStore
import pinecone
import schedule
import time
from datetime import datetime, timedelta
import threading
from googleapiclient.http import MediaIoBaseUpload
import io
from llama_index.llms.anthropic import Anthropic
from config import qna_system_prompt


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# ... (keep the authenticate_google_drive function as before)

# Set up Pinecone
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index_name = "googledrive-qa"
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=384,
        metric="cosine",
        spec=ServerlessSpec(
            cloud='aws',
            region='us-east-1'
        )
    )
pinecone_index = pc.Index(index_name)

# Global variables
index = None
last_update_time = None
query_engine = None

@st.cache_resource
def get_query_engine():
    global index, query_engine
    if index is None:
        # Initialize index here if needed
        vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_documents([], storage_context=storage_context)
    if query_engine is None:
        llm = Anthropic(model="claude-3-5-sonnet-20240620",system_prompt = qna_system_prompt )
        query_engine = index.as_query_engine(llm=llm)
    return query_engine

"""

"""
def process_google_drive(credentials, folder_id, force_update=False):
    global index

    # Build the Drive service
    drive_service = build('drive', 'v3', credentials=credentials)

    # Read the last update time from Google Drive
    last_update_file_id = st.session_state.get('last_update_file_id')
    last_update_time = None
    if last_update_file_id:
        last_update_time = read_last_update_time(drive_service, last_update_file_id)

    # Check if an update is needed
    current_time = datetime.utcnow()
    if last_update_time and not force_update:
        time_since_last_update = current_time - last_update_time
        if time_since_last_update < timedelta(weeks=1):
            logging.info("No update needed. Last update was less than a week ago.")
            return
    # Check if the index already exists in Pinecone.
    # We only process all documents if the index is empty or if a forced update is triggered.
    if pinecone_index.describe_index_stats()['total_vector_count'] > 0:
        logging.info("Index already exists. Skipping initial document insertion.")
        return
    # Initialize GoogleDriveReader
    gdrive_reader = GoogleDriveReader(credentials=credentials)

    # Read documents from the specified folder
    if last_update_time:
        query = f"'{folder_id}' in parents and modifiedTime > '{last_update_time.isoformat()}'"
        documents = gdrive_reader.load_data(folder_id=folder_id, query=query)
    else:
        documents = gdrive_reader.load_data(folder_id=folder_id)

    if not documents:
        logging.info("No new or modified documents found.")
        return

    # Update the index
    vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    if index is None: # TODO: check when will the index NOt be none
        index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
    else:
        for doc in documents:
            index.insert(doc)

    # Write the new last update time to Google Drive
    file_id = write_last_update_time(drive_service, last_update_file_id, current_time)
    if file_id:
        st.session_state.last_update_file_id = file_id

    logging.info(f"Processed {len(documents)} new or modified documents.")


def get_file_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"



##Also, ensure that your Google Drive API credentials have the necessary permissions to create and update files.
def update_index():
    logging.info("Running weekly update...")
    process_google_drive(st.session_state.credentials, st.session_state.folder_id, force_update=True)
    logging.info("Update completed. Next update scheduled for one week from now.")


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

def read_last_update_time(drive_service, file_id):
    try:
        # file = drive_service.files().get(fileId=file_id).execute()
        content = drive_service.files().get_media(fileId=file_id).execute()
        return datetime.fromisoformat(content.decode())
    except Exception as e:
        logging.error(f"Error reading last update time: {e}")
        return None

def write_last_update_time(drive_service, file_id, last_update_time):
    try:
        file_metadata = {'name': 'last_update_time.txt'}
        media = MediaIoBaseUpload(io.BytesIO(last_update_time.isoformat().encode()),
                                  mimetype='text/plain')
        if file_id:
            file = drive_service.files().update(fileId=file_id,
                                                media_body=media).execute()
        else:
            file = drive_service.files().create(body=file_metadata,
                                                media_body=media,
                                                fields='id').execute()
        return file.get('id')
    except Exception as e:
        logging.error(f"Error writing last update time: {e}")
        return None