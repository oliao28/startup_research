import os
import logging
import streamlit as st
from pinecone import Pinecone, ServerlessSpec
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.llms.anthropic import Anthropic
from config import qna_system_prompt
os.environ["PINECONE_API_KEY"]=st.secrets["pinecone_api_key"]
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up Pinecone
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index_name = "googledrive-qa"
pinecone_index = pc.Index(index_name)
#Debug
stats = pinecone_index.describe_index_stats()
print(f"Total vectors in index: {stats['total_vector_count']}")
logging.info(f"Successfully connected to Pinecone. Index stats: {stats}")
# Global variables
index = None
query_engine = None

@st.cache_resource
def get_query_engine():
    global index, query_engine
    if index is None:
        vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
        index = VectorStoreIndex.from_vector_store(vector_store)
        logging.info(f"Initialize index = {index}")
    if query_engine is None:
        logging.info("Create query engine")
        llm = Anthropic(model="claude-3-5-sonnet-20240620", system_prompt=qna_system_prompt)
        query_engine = index.as_query_engine(llm=llm)
    logging.info(f"Query engine created: {query_engine}")
    return query_engine

#Debug
def test_query_engine():
    logging.info(f"Anthropic API key set: {'ANTHROPIC_API_KEY' in os.environ}")
    query_engine = get_query_engine()
    test_question = "What is Darwin?"
    response = query_engine.query(test_question)
    logging.info(f"Test question: {test_question}")
    logging.info(f"Response: {response.response}")
    logging.info(f"Source nodes: {response.source_nodes}")


def get_file_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"
