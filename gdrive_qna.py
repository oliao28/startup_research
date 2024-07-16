import os
import logging
import streamlit as st
from pinecone import Pinecone, ServerlessSpec
import time
import torch
from typing import List, Optional,  Dict, ClassVar
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, ServiceContext
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.llms.anthropic import Anthropic
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.postprocessor import LongContextReorder
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.postprocessor.types import BaseNodePostprocessor


# from llama_index.core import set_global_handler
# general usage
# set_global_handler("<handler_name>", **kwargs)

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
            # Adjust score based on document length. Once the document has more than 100 words, the score returns to the original score
            length_factor = min(len(node.text.split()) / 100, 1)  # Normalize to max of 1
            node.score *= (0.5 + 0.5 * length_factor)  # Blend original score with length factor
        return sorted(nodes, key=lambda x: x.score, reverse=True)


@st.cache_resource
def get_query_engine(question_info = None):
    global index, llm #, performance_callback
    # if performance_callback is None:
    #     performance_callback = PerformanceCallback()
    if index is None:
        vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
        embed_model = HuggingFaceEmbedding(
            model_name="intfloat/multilingual-e5-base",
            device="cuda" if torch.cuda.is_available() else "cpu"
        )
        service_context = ServiceContext.from_defaults(
            embed_model=embed_model,
            # callback_manager=callback_manager
        )

        index = VectorStoreIndex.from_vector_store(
            vector_store,
            service_context=service_context
        )
        logging.info(f"Initialize index = {index}")

    if llm is None:
        llm = Anthropic(model="claude-3-5-sonnet-20240620", system_prompt=qna_system_prompt)

    # Create query engine with hybrid retriever
    reorder = CustomLongContextReorder()
    # reorder = LengthAwareSimilarityPostprocessor(similarity_cutoff=0.7)
    query_engine = index.as_query_engine(
        vector_store_query_mode="hybrid",
        node_postprocessors=[reorder],
        similarity_top_k=20, #5,
        alpha=0.5,  # This controls the balance between vector and keyword search
        # filters=filters,
        vector_store_kwargs={
            "filter": question_info,
        },
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
    if file_id:
        return f"https://drive.google.com/file/d/{file_id}/view"

def extract_unique_top_3(ranked_list):
    seen = set()
    result = []
    for item in ranked_list:
        if len(result) == 3:
            break
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class CustomLongContextReorder(BaseNodePostprocessor):
    """
    Models struggle to access significant details found
    in the center of extended contexts. A study
    (https://arxiv.org/abs/2307.03172) observed that the best
    performance typically arises when crucial data is positioned
    at the start or conclusion of the input context. Additionally,
    as the input context lengthens, performance drops notably, even
    in models designed for long contexts.".
    Logic: first separate (docx or xlsx) and the rest of files. Then within
    each file group, perform the long context method
    """
    @classmethod
    def class_name(cls) -> str:
        return "CustomLongContextReorder"
    file_type_weights: ClassVar[Dict[str, float]] = {
        ".docx": 1.15,
        ".xlsx": 1.25
    }
    @classmethod
    def with_custom_weights(cls, docx_weight: float = 1.2, xlsx_weight: float = 1.15):
        instance = cls()
        instance.file_type_weights = {
            ".docx": docx_weight,
            ".xlsx": xlsx_weight,
            ".xls": xlsx_weight
        }
        return instance

    def _process_nodes_long_context(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        # Reorder nodes based on long context method
        reordered_nodes: List[NodeWithScore] = []
        ordered_nodes: List[NodeWithScore] = sorted(
            nodes, key=lambda x: x.score if x.score is not None else 0
        )
        for i, node in enumerate(ordered_nodes):
            if i % 2 == 0:
                reordered_nodes.insert(0, node)
            else:
                reordered_nodes.append(node)
        return reordered_nodes
    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        """Postprocess nodes."""
        # Apply file type weights to scores
        node_first: List[NodeWithScore] = []
        node_secondary: List[NodeWithScore] = []
        for node in nodes:
            file_type = node.node.metadata.get("file type", "unknown")
            weight = self.file_type_weights.get(file_type, 1.0)
            if node.score is not None:
                node.score *= weight
            if weight> 1:
                node_first.append(node)
            else:
                node_secondary.append(node)
        final_nodes = self._process_nodes_long_context(node_first)+ self._process_nodes_long_context(node_secondary)
        # tmp = [(node.node.metadata.get("file name"), node.score) for node in final_nodes]
        # print(f'final order is {tmp}')
        return final_nodes


# class PerformanceCallback(BaseCallbackHandler):
#     def __init__(self, event_starts_to_ignore: Optional[Set[str]] = None,
#                  event_ends_to_ignore: Optional[Set[str]] = None):
#         super().__init__(event_starts_to_ignore or set(), event_ends_to_ignore or set())
#         self.start_time = None
#         self.total_latency = 0
#         self.num_queries = 0
#         self.num_retrieved_nodes = 0
#
#     def on_event_start(
#                 self,
#                 event_type: str,
#                 payload: Optional[dict] = None,
#                 event_id: Optional[str] = None,
#                 parent_id: Optional[str] = None,
#                 **kwargs: Any,
#         ) -> str:
#             if event_type == "retrieve":
#                 self.start_time = time.time()
#             elif event_type == "query":
#                 self.num_queries += 1
#             return event_id or ""
#
#     def on_event_end(
#             self,
#             event_type: str,
#             payload: Optional[dict] = None,
#             event_id: Optional[str] = None,
#             **kwargs: Any,
#     ) -> None:
#         if event_type == "retrieve":
#             if self.start_time is not None:
#                 self.total_latency += time.time() - self.start_time
#                 self.start_time = None
#             if payload and "nodes" in payload:
#                 self.num_retrieved_nodes += len(payload["nodes"])
#
#     def get_metrics(self):
#         avg_latency = self.total_latency / self.num_queries if self.num_queries > 0 else 0
#         avg_nodes_retrieved = self.num_retrieved_nodes / self.num_queries if self.num_queries > 0 else 0
#         return {
#             "num_queries": self.num_queries,
#             "avg_total_latency": avg_latency,
#             "avg_nodes_retrieved": avg_nodes_retrieved
#         }
#
#     def start_trace(self, trace_id: Optional[str] = None) -> None:
#         pass
#
#     def end_trace(
#         self,
#         trace_id: Optional[str] = None,
#         trace_map: Optional[dict] = None,
#     ) -> None:
#         pass
#
#     def on_event_start(
#         self,
#         event_type: str,
#         payload: Optional[dict] = None,
#         event_id: Optional[str] = None,
#         parent_id: Optional[str] = None,
#         **kwargs: Any,
#     ) -> str:
#         return event_id or ""
#
#     def on_event_end(
#         self,
#         event_type: str,
#         payload: Optional[dict] = None,
#         event_id: Optional[str] = None,
#         **kwargs: Any,
#     ) -> None:
#         pass
#
#     def flush(self) -> None:
#         pass
#
#     def handle_event(
#         self,
#         event_type: str,
#         payload: Optional[dict] = None,
#         event_id: Optional[str] = None,
#         parent_id: Optional[str] = None,
#         **kwargs: Any
#     ) -> None:
#         pass

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
