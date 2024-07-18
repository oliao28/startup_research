import os
import logging
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from pinecone import Pinecone, ServerlessSpec
from llama_index.core import VectorStoreIndex, StorageContext, ServiceContext
from llama_index.core import Settings
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import torch

from base import GoogleDriveReader #copied the base file from llama_index to fix some errors
import pytz
taipei_tz = pytz.timezone('Asia/Taipei')

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up a separate file handler for specific error messages
file_handler = logging.FileHandler('error_indexing_file.txt')
file_handler.setLevel(logging.ERROR)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s'))

# Create a separate logger for file logging
file_index_logger = logging.getLogger('file_index_logger')
file_index_logger.addHandler(file_handler)
file_index_logger.setLevel(logging.ERROR)

# Set up Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive']

# Set up Pinecone
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index_name = "googledrive-qa"
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=768,
        metric="cosine",
        spec=ServerlessSpec(
            cloud='aws',
            region='us-east-1'
        )
    )
pinecone_index = pc.Index(index_name)

LAST_UPDATE_FILE = 'last_update_time.txt'
PROCESSED_FOLDERS_FILE = 'processed_folders.txt'


# def authenticate_google_drive():
#     creds = Credentials.from_authorized_user_file('token.json', SCOPES)
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             raise ValueError("Invalid credentials. Please run the authentication flow separately.")
#     return creds

from google_auth_oauthlib.flow import InstalledAppFlow, Flow
def authenticate_google_drive(): #TODO: need to make it work with Streamlit cloud. Try running quickstart.py
    creds = None
    if os.path.exists('token.json'):
        logging.info("Automatically authentication")
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid or creds.expired:
        logging.info("Initialize an authentication")
        flow = InstalledAppFlow.from_client_secrets_file(
            "desk_credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=8001, prompt='consent')

        with open('token.json', 'w') as token:
            logging.info("Create token file")
            token.write(creds.to_json())

    return creds


def read_last_update_time():
    try:
        if os.path.exists(LAST_UPDATE_FILE):
            with open(LAST_UPDATE_FILE, 'r') as f:
                return datetime.fromisoformat(f.read().strip())
    except Exception as e:
        logging.error(f"Error reading last update time: {e}")
    return None


def write_last_update_time(last_update_time): #write to a file in Github
    try:
        with open(LAST_UPDATE_FILE, 'w') as f:
            f.write(last_update_time.isoformat())
        logging.info(f"Updated {LAST_UPDATE_FILE}")
    except Exception as e:
        logging.error(f"Error writing last update time: {e}")


def read_processed_folders():
    try:
        if os.path.exists(PROCESSED_FOLDERS_FILE):
            with open(PROCESSED_FOLDERS_FILE, 'r') as f:
                return set(f.read().splitlines())
    except Exception as e:
        logging.error(f"Error reading processed folders: {e}")
    return set()


def write_processed_folders(folders):
    try:
        with open(PROCESSED_FOLDERS_FILE, 'w') as f:
            for folder in folders:
                f.write(f"{folder}\n")
        logging.info(f"Updated {PROCESSED_FOLDERS_FILE}")
    except Exception as e:
        logging.error(f"Error writing processed folders: {e}")


def get_folders(drive_service, parent_folder_id):
    query = f"'{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder'"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    return {folder['name']: folder['id'] for folder in results.get('files', [])}

def set_to_list(item):
    return list(item) if isinstance(item, set) else item

def process_google_drive(credentials, parent_folder_id):
    drive_service = build('drive', 'v3', credentials=credentials)
    gdrive_reader = GoogleDriveReader(credentials=credentials)
    # Upload Darwin 20xx partitioned folders
    #-----------------------------------------
    folders = get_folders(drive_service, parent_folder_id)
    folders = folders.items()
    folders = [folder for folder in folders if folder[0].startswith("Darwin")]
    processed_folders = set_to_list(read_processed_folders())
    # Sort folders by year (assuming folder names end with a year)
    sorted_folders = sorted(
        [folder for folder in folders if len(folder[0].split()) > 1 and folder[0].split()[1].isdigit()],
        key=lambda x: int(x[0].split()[1]),
        reverse=True
    )
    num_folders = 2 if processed_folders else len(sorted_folders)
    folders_to_process = sorted_folders[:num_folders]  # Process only the latest two folders
    folders_to_process = [x for x in folders_to_process if x[0]!="Darwin 2024 BP"]#TODO: delete this
    logging.info(f"Folders to be processed: {folders_to_process}")

    # Create the embedding model
    embed_model = HuggingFaceEmbedding(
        model_name="intfloat/multilingual-e5-base",
        device="cuda" if torch.cuda.is_available() else "cpu"
    )
    Settings.embed_model = embed_model
    all_docs = []
    for folder_name, folder_id in folders_to_process:
        year = folder_name.split()[1]  # Extract year from folder name
        if folder_name not in processed_folders:
            query = f"'{folder_id}' in parents"
            logging.info(f"Processing all documents in new folder: {folder_name}")
        else:
            last_update_time = read_last_update_time()
            if last_update_time:
                query = f"'{folder_id}' in parents and modifiedTime > '{last_update_time.isoformat()}'"
                logging.info(f"Updating documents modified after {last_update_time} in folder: {folder_name}")
            else:
                query = f"'{folder_id}' in parents"
                logging.info(f"Processing all documents in folder: {folder_name} (no last update time found)")

        documents = gdrive_reader.load_data(folder_id=folder_id, query_string=query)
        logging.info(f"Loaded {len(documents)} documents from Gdrive ")
        if documents:
            # Process each document to update metadata
            for doc in documents:
                # Get the subfolder name
                file_path = doc.metadata.get('full path')
                company = file_path.split("/")[0]
                # Update metadata
                new_metadata = {
                    'file name': doc.metadata.get('file name'),
                    'file id': doc.metadata.get('file id'),
                    'year': year,
                    'company': company.capitalize(),
                    'file type': doc.metadata.get('file type'),
                    'modified at': doc.metadata.get('modified at'),
                }
                doc.metadata = new_metadata
            import pickle
            with open(f'documents_{year}.pkl', 'wb') as f:
                pickle.dump(documents, f)
            # all_docs.append(set_to_list(documents))
            vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            try:
               VectorStoreIndex.from_documents(documents, storage_context=storage_context,
                                            embed_model=embed_model)
               logging.info(f"Processed {len(documents)} documents in folder: {folder_name}")
            except Exception as e:
               file_index_logger.error(f"Error indexing the documents: {e}")
            if folder_name not in processed_folders:
                processed_folders.add(folder_name)
        else:
            logging.info(f"No new or modified documents found in folder: {folder_name}")

    all_processed = [x[0] for x in folders_to_process]+processed_folders
    print(all_processed)
    write_processed_folders(list(set(all_processed)))
    write_last_update_time(datetime.now(taipei_tz))
    return all_docs
def main():
    credentials = authenticate_google_drive()
    # folder_id ='1UzLrdbCOVIQYUesYpw3z2KOxs5bfU18-'  #BP_test_olivia/Darwin 2023 BP/swif <-- success processed 1 documents
    # folder_id ='172HNsBCZ30JcmHzmMmVMI6EN68u2PnWq' #BP_test_olivia/Darwin 2023 BP <-- no errors but processed zero documents
    # folder_id ='1D403KctcPHAHmszLwFpNXw_-wOs1Ulwp' #BP_test_olivia/Darwin 2022 BP
    # folder_id ='1ZIcgpzXzkIGfE2way2oh3viRK9Xpz6ud' #BP/Darwin 2023 BP/Olivia_test <-- no errors but processed zero documents
    # folder_id ='1W38m1nqmKrZ-Qykm6eB2toOLcTIOE0vt' #BP/Darwin 2023 BP/Olivia_test2 <-- no errors but processed zero documents
    # folder_id ='1flkALOgcO9X_oSmp9i-Hdb1xtzseJRsd' #BP_test_olivia  <-- no errors but processed zero documents
    folder_id ='1p5_PIIvXEGckI1LP-Tvnn3Ajt0XDCtVH' #BP
    all_docs = process_google_drive(credentials, folder_id)
    # import pickle
    # with open('all_docs.pickle', 'wb') as handle:
    #     pickle.dump(all_docs, handle, protocol=pickle.HIGHEST_PROTOCOL)

if __name__ == "__main__":
    main()
