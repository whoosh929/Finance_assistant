from typing import List

from langchain.chains.llm import LLMChain
from langchain.base_language import BaseLanguageModel
from langchain.chains import (
    RetrievalQAWithSourcesChain,
    StuffDocumentsChain,
    ReduceDocumentsChain,
)
from langchain.schema import Document
from langchain.chains.summarize import load_summarize_chain

from src.utilities.token_helper import num_tokens_from_string

from src.db.models.conversations import SearchType
from src.db.models.documents import Documents
from src.db.models.pgvector_retriever import PGVectorRetriever

from src.ai.interactions.interaction_manager import InteractionManager


class DocumentTool:
    def __init__(
        self,
        configuration,
        interaction_manager: InteractionManager,
        llm: BaseLanguageModel,
    ):
        self.configuration = configuration
        self.interaction_manager = interaction_manager
        self.llm = llm

    def search_loaded_documents(
        self,
        semantic_similarity_query: str,
        keywords_list: List[str],
        user_query: str,
        target_file_id: int = None,
    ):
        """Searches the loaded files (or the specified file when target_file_id is set) for the given query.
        The target_file_id argument is optional, and can be used to search a specific file if the user has specified one.

        IMPORTANT: If the user has not asked you to look in a specific file, don't use target_file_id.

        Args:
            similarity_query (str): The query to search the loaded documents for (can be a modified version of the original_user_input for searching).
            keywords_list (str): A keyword version of the query to search the loaded documents for
            original_user_input (str): The original user input.  Make sure this is not modified by you!
            target_file_id (int, optional): The file_id if you want to search a specific file. Defaults to None which searches all files.
        """

        target_file_id = self.interaction_manager.tool_kwargs.get(
            "override_file", target_file_id
        )

        keyword_documents = (
            self.interaction_manager.documents_helper.search_document_embeddings(
                search_query=keywords_list,
                collection_id=self.interaction_manager.collection_id,
                search_type=SearchType.Keyword,
                top_k=self.interaction_manager.tool_kwargs.get("search_top_k", 5),
                target_file_id=target_file_id,
            )
        )

        similarity_documents = (
            self.interaction_manager.documents_helper.search_document_embeddings(
                search_query=semantic_similarity_query,
                collection_id=self.interaction_manager.collection_id,
                search_type=SearchType.Similarity,
                top_k=self.interaction_manager.tool_kwargs.get("search_top_k", 5),
                target_file_id=target_file_id,
            )
        )

        # De-dupe the documents
        combined_documents = []
        document_ids = []
        for document in keyword_documents:
            if document.id not in document_ids:
                combined_documents.append(document)
                document_ids.append(document.id)

        for document in similarity_documents:
            if document.id not in document_ids:
                combined_documents.append(document)
                document_ids.append(document.id)

        prompt = self.interaction_manager.prompt_manager.get_prompt(
            "document", "QUESTION_PROMPT_TEMPLATE"
        )

        # prompt_tokens = num_tokens_from_string(prompt + original_user_input)

        # Examine each of the documents to see if they have anything relating to the original query
        # TODO: Split the documents up into chunks that fit within the max tokens - the completion no matter what the top_k is

        summaries = []

        for document in combined_documents:
            page_or_line = (
                f"page='{document.additional_metadata['page']}'"
                if "page" in document.additional_metadata
                else f"line='{document.additional_metadata['start_line']}'"
            )
            summaries.append(
                f"CONTENT: \n{document.document_text}\nSOURCE: file_id='{document.file_id}', file_name='{document.document_name}', {page_or_line}"
            )

        prompt = prompt.format(summaries="\n\n".join(summaries), question=user_query)

        result = self.llm.predict(prompt)

        return result

    def generate_detailed_document_chunk_summary(
        self,
        document_text: str,
    ) -> str:
        summary = self.llm.predict(
            self.interaction_manager.prompt_manager.get_prompt(
                "summary",
                "DETAILED_DOCUMENT_CHUNK_SUMMARY_TEMPLATE",
            ).format(text=document_text)
        )
        return summary

    # TODO: Replace this summarize with a summarize call when ingesting documents.  Store the summary in the DB for retrieval here.
    def summarize_entire_document(self, target_file_id: int):
        """Useful for getting a summary of an entire specific document.  The target_file_id argument is required.

        Args:

            target_file_id (int): The file_id you got from the list of loaded files"""
        # Create the documents class for the retriever
        documents = Documents()
        file = documents.get_file(target_file_id)

        # Is there a summary already?  If so, return that instead of re-running the summarization.
        if file.file_summary and file.file_summary != "":
            return file.file_summary

        # Get the document chunks
        document_chunks = documents.get_document_chunks_by_file_id(
            target_file_id=target_file_id
        )

        # Are there already document chunk summaries?
        for chunk in document_chunks:
            if not chunk.document_text_has_summary:
                # Summarize the chunk
                summary_chunk = self.generate_detailed_document_chunk_summary(
                    chunk.document_text
                )
                documents.set_document_text_summary(chunk.id, summary_chunk)

        reduce_chain = LLMChain(
            llm=self.llm,
            prompt=self.interaction_manager.prompt_manager.get_prompt(
                "summary",
                "REDUCE_SUMMARIES_PROMPT",
            ),
        )

        # Takes a list of documents, combines them into a single string, and passes this to an LLMChain
        combine_documents_chain = StuffDocumentsChain(
            llm_chain=reduce_chain, document_variable_name="doc_summaries"
        )

        # Combines and iteravely reduces the document summaries
        reduce_documents_chain = ReduceDocumentsChain(
            # This is final chain that is called.
            combine_documents_chain=combine_documents_chain,
            # If documents exceed context for `StuffDocumentsChain`
            collapse_documents_chain=combine_documents_chain,
            # The maximum number of tokens to group documents into.
            token_max=self.interaction_manager.tool_kwargs.get(
                "max_summary_chunk_tokens", 5000
            ),
        )

        document_chunks = documents.get_document_chunks_by_file_id(target_file_id)

        docs = [
            Document(
                page_content=doc_chunk.document_text_summary,
                metadata=doc_chunk.additional_metadata,
            )
            for doc_chunk in document_chunks
        ]

        summary = reduce_documents_chain.run(docs)

        # Put the summary into the DB so we don't have to re-run this.
        documents.update_file_summary_and_class(
            file_id=file.id, summary=summary, classification=file.file_classification
        )

        return summary

    def summarize_search_topic(self, query: str, original_user_query: str):
        """Useful for getting a summary of a topic or query from the user.
        This looks at all loaded documents for the topic specified by the query and return a summary of that topic.

        Args:

            query (str, Required): The query to search the loaded documents for (this can be a modified version of the original_user_query for searching).
            original_user_query (str, Required): The original user input.  Make sure this is not modified by you!
        """
        # Create the documents class for the retriever
        documents = Documents()

        document_models = documents.search_document_embeddings(
            search_query=query,
            collection_id=self.interaction_manager.collection_id,
            search_type=self.interaction_manager.tool_kwargs.get(
                "search_method", SearchType.Similarity
            ),
            target_file_id=self.interaction_manager.tool_kwargs.get(
                "override_file", None
            ),
            top_k=self.interaction_manager.tool_kwargs.get("search_top_k", 5),
        )

        # Convert the document models to Document classes
        docs = []
        for doc in document_models:
            docs.append(
                Document(
                    page_content=doc.document_text, metadata=doc.additional_metadata
                )
            )

        summary = self.refine_summarize(llm=self.llm, query=query, docs=docs)

        if self.interaction_manager.tool_kwargs.get("re_run_user_query", False):
            summary = self.llm.predict(
                f"Using the following context derived by searching documents, answer the user's original query.\n\nCONTEXT:\n{summary}\n\nORIGINAL QUERY:\n{original_user_query}\n\nAI: I have examined the context above and have determined the following (my response in Markdown):\n"
            )

        return summary

    # def map_reduce_summarize(self, query, llm, docs):
    #     pass
    #     # chain = load_summarize_chain(
    #     #     llm=llm,
    #     #     chain_type="refine",
    #     #     question_prompt=self.interaction_manager.prompt_manager.get_prompt(
    #     #         "document", "DETAILED_SUMMARIZE_PROMPT"
    #     #     ),
    #     #     refine_prompt=self.interaction_manager.prompt_manager.get_prompt(
    #     #         "document", "SIMPLE_REFINE_PROMPT"
    #     #     ),
    #     #     return_intermediate_steps=True,
    #     #     input_key="input_documents",
    #     #     output_key="output_text",
    #     # )

    #     # result = chain({"input_documents": docs, "query": query}, return_only_outputs=True)

    #     # return result["output_text"]

    def refine_summarize(self, llm, docs, query: str | None = None):
        if query is None:
            refine_prompt = "SIMPLE_DOCUMENT_REFINE_PROMPT"
        else:
            refine_prompt = "SIMPLE_REFINE_PROMPT"

        chain = load_summarize_chain(
            llm=llm,
            chain_type="refine",
            question_prompt=self.interaction_manager.prompt_manager.get_prompt(
                "summary",
                "DETAILED_SUMMARIZE_PROMPT",
            ),
            refine_prompt=self.interaction_manager.prompt_manager.get_prompt(
                "summary", refine_prompt
            ),
            return_intermediate_steps=True,
            input_key="input_documents",
            output_key="output_text",
            verbose=True,
        )

        if query is None:
            result = chain({"input_documents": docs}, return_only_outputs=True)
        else:
            result = chain(
                {"input_documents": docs, "query": query}, return_only_outputs=True
            )

        return result["output_text"]

    def list_documents(self):
        """Useful for discovering which documents or files are loaded or otherwise available to you.
        Always use this tool to get the file ID (if you don't already know it) before calling anything else that requires it.
        """

        return "The loaded documents I have access to are:\n\n-" + "\n-".join(
            self.interaction_manager.get_loaded_documents_for_display()
        )
