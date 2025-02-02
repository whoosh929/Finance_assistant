import sys
import os
import logging
import json
from typing import List

from langchain.base_language import BaseLanguageModel

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from src.db.models.documents import Documents
from src.ai.interactions.interaction_manager import InteractionManager

from src.utilities.token_helper import num_tokens_from_string


from src.integrations.gitlab.gitlab_issue_creator import GitlabIssueCreator
from src.integrations.gitlab.gitlab_issue_retriever import GitlabIssueRetriever
from src.integrations.gitlab.gitlab_file_retriever import GitlabFileRetriever

from src.integrations.github.github_file_retriever import GitHubFileRetriever


class CodeReviewTool:
    source_control_to_file_retriever_map: dict = {
        "gitlab": GitlabFileRetriever,
        "github": GitHubFileRetriever,
    }
    source_control_to_issue_creator_map: dict = {
        "gitlab": GitlabIssueCreator,
        "github": None,
    }
    source_control_to_issue_retriever_map: dict = {
        "gitlab": GitlabIssueRetriever,
        "github": None,
    }

    def __init__(
        self,
        configuration,
        interaction_manager: InteractionManager,
        llm: BaseLanguageModel,
    ):
        self.configuration = configuration
        self.interaction_manager = interaction_manager
        self.llm = llm

    def ingest_source_code_file_from_url(self, url):
        source_control_provider = os.getenv("SOURCE_CONTROL_PROVIDER", "GitHub")
        file_retriever = self.source_control_to_file_retriever_map[
            source_control_provider.lower()
        ]
        if not file_retriever:
            return f"Source control provider {source_control_provider} does not support file retrieval"

        file_retriever = file_retriever(
            source_control_url=os.getenv("source_control_url"),
            source_control_pat=os.getenv("source_control_pat"),
        )

        return file_retriever.retrieve_file_data(url=url)
    

    def ingest_issue_from_url(self, url):
        source_control_provider = os.getenv("SOURCE_CONTROL_PROVIDER", "GitHub")
        retriever = self.source_control_to_issue_retriever_map[
            source_control_provider.lower()
        ]
        if not retriever:
            return f"Source control provider {source_control_provider} does not support issue retrieval"

        retriever = retriever(
            source_control_url=os.getenv("source_control_url"),
            source_control_pat=os.getenv("source_control_pat"),
        )

        return retriever.retrieve_issue_data(url=url)

    def create_code_review_issue_tool(
        self,
        project_id: int,
        ref: str,
        source_code_file_href: str,
        source_code_file_path: str,
        review_data: dict,
    ):
        """
        Creates an issue containing the code review for a single reviewed file,on the source code control system specified

        # Args:
        #     source_code_file_data: A dictionary containing the project ID, file URL, file relative path, ref name, file contents
        #     review_data: A python dictionary containing the code review data to create the issue from
        """
        source_control_provider = os.getenv("SOURCE_CONTROL_PROVIDER", "GitHub")
        issue_creator = self.source_control_to_issue_creator_map[
            source_control_provider.lower()
        ]
        if not issue_creator:
            return f"Source control provider {source_control_provider} does not support issue creation"

        issue_creator = issue_creator(
            source_control_url=os.getenv("source_control_url"),
            source_control_pat=os.getenv("source_control_pat"),
        )

        result = issue_creator.generate_issue(
            project_id=project_id,
            ref=ref,
            source_code_file_loc=source_code_file_path,
            source_code_file_href=source_code_file_href,
            review_data=review_data,
        )

        return f"Successfully created issue at {result['url']}"

    def conduct_code_review(
        self,
        file_data: str,
        additional_instructions: str = None,
        code_metadata: dict = None,
        previous_issue=None,
    ):
        max_code_review_token_count = self.interaction_manager.tool_kwargs.get(
            "max_code_review_token_count", 5000
        )
        code_file_token_count = num_tokens_from_string(file_data)
        if code_file_token_count > max_code_review_token_count:
            return f"File is too large to be code reviewed ({code_file_token_count} tokens). Adjust max code review tokens, or refactor this code file so that it's smaller."

        code = file_data.splitlines()
        for line_num, line in enumerate(code):
            code[line_num] = f"{line_num}: {line}"

        base_code_review_instructions = (
            self.interaction_manager.prompt_manager.get_prompt(
                "code_review", "BASE_CODE_REVIEW_INSTRUCTIONS_TEMPLATE"
            )
        )

        final_code_review_instructions = (
            self.interaction_manager.prompt_manager.get_prompt(
                "code_review", "FINAL_CODE_REVIEW_INSTRUCTIONS"
            ).format(
                code_summary="",
                code_dependencies="",
                code=code,
                code_metadata=code_metadata,
                additional_instructions=additional_instructions,
            )
        )

        # TODO: Refactor this so Jordan is happy
        # ,
        templates = [
            "SECURITY_CODE_REVIEW_TEMPLATE",
            "PERFORMANCE_CODE_REVIEW_TEMPLATE",
            "MEMORY_CODE_REVIEW_TEMPLATE",
            "CORRECTNESS_CODE_REVIEW_TEMPLATE",
            "MAINTAINABILITY_CODE_REVIEW_TEMPLATE",
            "RELIABILITY_CODE_REVIEW_TEMPLATE",
        ]

        review_results = {}
        comment_results = []
        for template in templates:
            code_review_prompt = self.interaction_manager.prompt_manager.get_prompt(
                "code_review", template
            ).format(
                base_code_review_instructions=base_code_review_instructions,
                final_code_review_instructions=final_code_review_instructions,
            )

            data = json.loads(self.llm.predict(code_review_prompt))
            comment_results.extend(data["comments"])

        review_results = {
            "language": data["language"],
            "metadata": data["metadata"],
            "comments": comment_results,
        }

        return review_results

    def conduct_code_review_from_url(
        self, target_url: str, additional_instructions: str = None
    ):
        """
        Conducts a code review for the specified file from a given target URL

        Args:
            target_url: The URL of the file to code review
        """
        if additional_instructions:
            additional_instructions = f"\nIn addition to the code review instructions, here are some additional instructions from the user that you should take into account when performing this code review:\n{additional_instructions}\n"
        else:
            additional_instructions = ""

        file_info = self.ingest_source_code_file_from_url(url=target_url)

        file_data = file_info["file_content"]
        code_metadata = {
            "project_id": file_info["project_id"],
            "url": file_info["url"],
            "ref": file_info["ref"],
            "file_path": file_info["file_path"],
        }
        previous_issue = self.ingest_issue_from_url(url=target_url)

        return self.conduct_code_review(
            file_data=file_data,
            additional_instructions=additional_instructions,
            code_metadata=code_metadata,
            previous_issue=previous_issue,
        )

    def conduct_code_review_from_file_id(
        self, target_file_id: int, additional_instructions: str = None
    ):
        """
        Conducts a code review for the specified file

        Args:
            target_file_id: The id of the file to conduct a code review on
        """

        if additional_instructions:
            additional_instructions = f"\n--- ADDITIONAL INSTRUCTIONS ---\n{additional_instructions}\n--- ADDITIONAL INSTRUCTIONS ---\n"
        else:
            additional_instructions = ""

        documents = Documents()

        # Get the list of documents
        file_model = documents.get_file(
            file_id=target_file_id,
        )

        if file_model.file_classification.lower() != "code":
            return "File is not code. Please select a code file to conduct a code review on, or use a different tool."

        # Convert file data bytes to string
        file_data = documents.get_file_data(file_model.id).decode("utf-8")

        return self.conduct_code_review(
            file_data=file_data,
            additional_instructions=additional_instructions,
            code_metadata={"filename": file_model.file_name},
        )


### This stuff probably needs to make its way back into the code review chain
# dependencies = self.code_tool.get_dependency_graph(
#     target_file_id=target_file_id
# )
# dependencies = "\n----- CODE DEPENDENCIES -----\n" + dependencies + "\n----- CODE DEPENDENCIES -----\n"

# document_tool = DocumentTool(
#     configuration=self.configuration,
#     interaction_manager=self.interaction_manager,
#     llm=self.llm,
# )

# summary = document_tool.summarize_entire_document(target_file_id=target_file_id)
# summary = "\n--- CODE SUMMARY ---\n" + summary + "\n--- CODE SUMMARY ---\n"
