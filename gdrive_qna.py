import os
import logging
import streamlit as st
from pinecone import Pinecone, ServerlessSpec
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.readers.google import GoogleDriveReader
from llama_index.vector_stores.pinecone import PineconeVectorStore
import time
from datetime import datetime, timedelta
from googleapiclient.http import MediaIoBaseUpload
import io
from llama_index.llms.anthropic import Anthropic
from config import qna_system_prompt
os.environ["PINECONE_API_KEY"]=st.secrets["pinecone_api_key"]


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive.file']

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
        logging.info("Initialize index")
        vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_documents([], storage_context=storage_context)
    if query_engine is None:
        logging.info("create query engine")
        llm = Anthropic(model="claude-3-5-sonnet-20240620", system_prompt = qna_system_prompt )
        query_engine = index.as_query_engine(llm=llm, streaming=True)
    return query_engine


def read_last_update_time(drive_service, file_id):
    try:
        file = drive_service.files().get(fileId=file_id).execute()
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
            logging.info("Update the update_time.txt")
            file = drive_service.files().update(fileId=file_id,
                                                media_body=media).execute()
        else:
            logging.info("Create an last_update_time.txt")
            file = drive_service.files().create(body=file_metadata,
                                                media_body=media,
                                                fields='id').execute()
        return file.get('id')
    except Exception as e:
        logging.error(f"Error writing last update time: {e}")
        return None
def get_or_create_last_update_file(drive_service, folder_id):
    query = f"name='last_update_time.txt' and '{folder_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])

    if files:
        logging.info(f"Get last update file: {files[0]['id']}")
        return files[0]['id']
    else:
        file_metadata = {
            'name': 'last_update_time.txt',
            'parents': [folder_id],
            'mimeType': 'text/plain'
        }
        file = drive_service.files().create(body=file_metadata, fields='id').execute()
        logging.info(f"Create last update file: {file.get('id')}")
        return file.get('id')


def check_and_update_index():
    while True:
        time.sleep(600)  # Wait for 10 minutes
        if 'last_activity' in st.session_state:
            time_since_last_activity = datetime.now() - st.session_state.last_activity
            if time_since_last_activity > timedelta(minutes=10):
                drive_service = build('drive', 'v3', credentials=st.session_state.credentials)
                if 'last_update_file_id' not in st.session_state or not st.session_state.last_update_file_id:
                    st.session_state.last_update_file_id = get_or_create_last_update_file(drive_service,
                                                                                          st.session_state.folder_id)

                last_update_time = read_last_update_time(drive_service, st.session_state.last_update_file_id)
                if last_update_time:
                    time_since_last_update = datetime.now() - last_update_time
                    if time_since_last_update > timedelta(weeks=1):
                        logging.info("Updating index after inactivity...")
                        new_last_update_time = process_google_drive(st.session_state.credentials,
                                                                    st.session_state.folder_id, last_update_time)
                        if new_last_update_time:
                            write_last_update_time(drive_service, st.session_state.last_update_file_id,
                                                   new_last_update_time)
                else:
                    # If we couldn't read the last update time (e.g. accidental deletion, we should probably update)
                    logging.info("No last update time found. Updating index...")
                    new_last_update_time = process_google_drive(st.session_state.credentials,
                                                                st.session_state.folder_id)
                    if new_last_update_time:
                        write_last_update_time(drive_service, st.session_state.last_update_file_id,
                                               new_last_update_time)


def process_google_drive(credentials, folder_id, last_update_time=None):
    global index

    drive_service = build('drive', 'v3', credentials=credentials)
    gdrive_reader = GoogleDriveReader(credentials=credentials)

    if last_update_time:
        query = f"'{folder_id}' in parents and modifiedTime > '{last_update_time.isoformat()}'"
        logging.info("partial update of Pinecone")
        documents = gdrive_reader.load_data(folder_id=folder_id, query=query)
    else:
        logging.info("full creation of Pinecone")
        documents = gdrive_reader.load_data(folder_id=folder_id)

    if not documents:
        logging.info("No new or modified documents found.")
        return

    vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    if index is None:
        index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
    else:
        for doc in documents:
            index.insert(doc)

    current_time = datetime.utcnow()
    file_id = write_last_update_time(drive_service, st.session_state.last_update_file_id, current_time)
    if file_id:
        st.session_state.last_update_file_id = file_id

    logging.info(f"Processed {len(documents)} documents.")
    return current_time  # Return the new last_update_time

def get_file_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"
