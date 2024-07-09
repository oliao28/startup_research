import os
import logging
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pinecone import Pinecone, ServerlessSpec
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.readers.google import GoogleDriveReader
from llama_index.vector_stores.pinecone import PineconeVectorStore

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Set up Pinecone
pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
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

def authenticate_google_drive():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise ValueError("Invalid credentials. Please run the authentication flow separately.")
    return creds

def process_google_drive(credentials, folder_id):
    # drive_service = build('drive', 'v3', credentials=credentials)
    gdrive_reader = GoogleDriveReader(credentials=credentials)

    logging.info("Full update of Pinecone")
    documents = gdrive_reader.load_data(folder_id=folder_id)

    if not documents:
        logging.info("No documents found.")
        return

    vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)

    logging.info(f"Processed {len(documents)} documents.")

def main():
    credentials = authenticate_google_drive()
    folder_id = '1JHdl4fsFJoysaByHMS1SCh7KO_EBqaS1'  # Replace with your actual folder ID
    process_google_drive(credentials, folder_id)

if __name__ == "__main__":
    main()

###--------------
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


def check_and_update_index(drive_service):
    current_time = datetime.now()

    if 'last_check_time' not in st.session_state:
        st.session_state.last_check_time = current_time - timedelta(minutes=10)  # Force first check

    time_since_last_check = current_time - st.session_state.last_check_time

    if time_since_last_check > timedelta(minutes=10):
        st.session_state.last_check_time = current_time

        if 'last_activity' in st.session_state:
            time_since_last_activity = current_time - st.session_state.last_activity
            if time_since_last_activity > timedelta(minutes=10):
                if 'last_update_file_id' not in st.session_state or not st.session_state.last_update_file_id:
                    st.session_state.last_update_file_id = get_or_create_last_update_file(drive_service,
                                                                                          st.session_state.folder_id)

                last_update_time = read_last_update_time(drive_service, st.session_state.last_update_file_id)
                if last_update_time:
                    time_since_last_update = current_time - last_update_time
                    if time_since_last_update > timedelta(weeks=1):
                        logging.info("Updating index after inactivity...")
                        new_last_update_time = process_google_drive(drive_service, st.session_state.folder_id,
                                                                    last_update_time)
                        if new_last_update_time:
                            write_last_update_time(drive_service, st.session_state.last_update_file_id,
                                                   new_last_update_time)
                else:
                    logging.info("No last update time found. Updating index...")
                    new_last_update_time = process_google_drive(drive_service, st.session_state.folder_id)
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
