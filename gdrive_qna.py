import os
import logging
import streamlit as st
from pinecone import Pinecone, ServerlessSpec
import time
import torch
from typing import Any, List, Optional, Set
from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler
from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, ServiceContext
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.llms.anthropic import Anthropic
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from config import qna_system_prompt
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global variables
index = None
llm = None
pinecone_index = None
performance_callback = None
def initialize_pinecone(api_key):
    global pinecone_index
    pc = Pinecone(api_key=api_key)
    pinecone_index = pc.Index("googledrive-qa")

class LengthAwareSimilarityPostprocessor(SimilarityPostprocessor):
    def postprocess_nodes(self, nodes, query_bundle):
        for node in nodes:
            # Adjust score based on document length
            length_factor = min(len(node.text.split()) / 100, 1)  # Normalize to max of 1
            node.score *= (0.5 + 0.5 * length_factor)  # Blend original score with length factor
        return sorted(nodes, key=lambda x: x.score, reverse=True)


@st.cache_resource
def get_query_engine(question_info = None):
    global index, llm, performance_callback
    if performance_callback is None:
        performance_callback = PerformanceCallback()
    if index is None:
        vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
        # Set up debug logging
        llama_debug = LlamaDebugHandler(print_trace_on_end=True)
        callback_manager = CallbackManager([llama_debug, performance_callback])

        # TODO:TEST THIS: Specify a multi-language model to deal with our Chinese & Japanese documents
        embed_model = HuggingFaceEmbedding(
            model_name="intfloat/multilingual-e5-large",
            device="cuda" if torch.cuda.is_available() else "cpu"
        )
        service_context = ServiceContext.from_defaults(
            embed_model=embed_model,
            callback_manager=callback_manager
        )

        index = VectorStoreIndex.from_vector_store(
            vector_store,
            service_context=service_context
        )
        logging.info(f"Initialize index = {index}")

    if llm is None:
        llm = Anthropic(model="claude-3-5-sonnet-20240620", system_prompt=qna_system_prompt)

    # Create query engine with hybrid retriever
    # reorder = LongContextReorder()
    reorder = LengthAwareSimilarityPostprocessor(similarity_cutoff=0.7)
    query_engine = index.as_query_engine(
        vector_store_query_mode="hybrid",
        node_postprocessors=[reorder],
        similarity_top_k=5,
        alpha=0.5,  # This controls the balance between vector and keyword search
        filters=question_info,
        llm=llm,
    )
    logging.info(f"Query engine created: {query_engine}")
    return query_engine

# def get_info_question(question):
#     """Return meta info about the question.
#
#     Args:
#         question: user input question
#     Returns:
#         info: dictionary, e.g. {"year":"2023", "company:"Swif"} or {"company:"Swif"}
#     """
#     #TODO: what small language model is specifically good at identifying patterns in a setence, e.g. find the company, find the year
#     #TODO: need to make sure company name is capitalized
#     #TODO: need to make sure we can search for company names in Chinese/Japanse
#     return info
def get_file_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"

class PerformanceCallback(BaseCallbackHandler):
    def __init__(self, event_starts_to_ignore: Optional[Set[str]] = None,
                 event_ends_to_ignore: Optional[Set[str]] = None):
        super().__init__(event_starts_to_ignore or set(), event_ends_to_ignore or set())
        self.start_time = None
        self.total_latency = 0
        self.num_queries = 0
        self.num_retrieved_nodes = 0

    def on_event_start(
                self,
                event_type: str,
                payload: Optional[dict] = None,
                event_id: Optional[str] = None,
                parent_id: Optional[str] = None,
                **kwargs: Any,
        ) -> str:
            if event_type == "retrieve":
                self.start_time = time.time()
            elif event_type == "query":
                self.num_queries += 1
            return event_id or ""

    def on_event_end(
            self,
            event_type: str,
            payload: Optional[dict] = None,
            event_id: Optional[str] = None,
            **kwargs: Any,
    ) -> None:
        if event_type == "retrieve":
            if self.start_time is not None:
                self.total_latency += time.time() - self.start_time
                self.start_time = None
            if payload and "nodes" in payload:
                self.num_retrieved_nodes += len(payload["nodes"])

    def get_metrics(self):
        avg_latency = self.total_latency / self.num_queries if self.num_queries > 0 else 0
        avg_nodes_retrieved = self.num_retrieved_nodes / self.num_queries if self.num_queries > 0 else 0
        return {
            "num_queries": self.num_queries,
            "avg_total_latency": avg_latency,
            "avg_nodes_retrieved": avg_nodes_retrieved
        }

    def start_trace(self, trace_id: Optional[str] = None) -> None:
        pass

    def end_trace(
        self,
        trace_id: Optional[str] = None,
        trace_map: Optional[dict] = None,
    ) -> None:
        pass

    def on_event_start(
        self,
        event_type: str,
        payload: Optional[dict] = None,
        event_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        return event_id or ""

    def on_event_end(
        self,
        event_type: str,
        payload: Optional[dict] = None,
        event_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        pass

    def flush(self) -> None:
        pass

    def handle_event(
        self,
        event_type: str,
        payload: Optional[dict] = None,
        event_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        pass

# #RERANKER option 1
#
# from llama_index.postprocessor import SimilarityPostprocessor
#
# #RERANKER OPTION 2
# class ContentRelevancePostprocessor(SimilarityPostprocessor):
#     def postprocess_nodes(self, nodes, query_bundle):
#         nodes = super().postprocess_nodes(nodes, query_bundle)
#         for node in nodes:
#             # Implement your content relevance scoring here
#             relevance_score = your_relevance_scoring_function(node.text, query_bundle.query_str)
#             node.score *= relevance_score
#         return sorted(nodes, key=lambda x: x.score, reverse=True)
#
# content_reranker = ContentRelevancePostprocessor(similarity_cutoff=0.7)
# query_engine = index.as_query_engine(
#     vector_store_query_mode="hybrid",
#     node_postprocessors=[content_reranker]
# )
# #RERANKER OPTION 3
# # Implement custom postprocessing
# # Custom postprocessor to consider document length
# reranker = LengthAwareSimilarityPostprocessor(similarity_cutoff=0.7)
