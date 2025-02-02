import logging
import time
from src.ai.abstract_ai import AbstractAI
from src.runners.runner import Runner
from src.db.database.models import User
from src.db.models.users import Users
from src.db.models.documents import Documents
from src.db.models.interactions import Interactions


from src.utilities.pretty_print import pretty_print_conversation


class ConsoleRunner(Runner):
    def __init__(self, interaction_id, collection_name, user_email):
        self.interaction_id = interaction_id
        self.collection_name = collection_name
        self.user_email = user_email        

        # Ensure the interaction exists
        self.ensure_interaction_exists()

        self.collection_id = self.ensure_collection_exists()

    def ensure_collection_exists(self):
        """Ensures that a collection exists for the current user"""

        documents_helper = Documents()     

        collection = documents_helper.get_collection_by_name(self.collection_name, self.interaction_id)            

        if collection is None:
            collection = documents_helper.create_collection(
                collection_name=self.collection_name,
                interaction_id=self.interaction_id,
            )        

        return collection.id

    def ensure_interaction_exists(self):
        """Ensures that an interaction exists for the current user"""

        interactions_helper = Interactions()   
        users_helper = Users()     
    
        interaction = interactions_helper.get_interaction(self.interaction_id)
        user_id = users_helper.get_user_by_email(self.user_email).id

        if interaction is None:
            interactions_helper.create_interaction(                
                id=self.interaction_id,
                interaction_summary="Console interaction",
                user_id=user_id
            )                    

    def configure(self):
        pass

    def run(self, abstract_ai: AbstractAI):

        while True:
            query = input("Query (X to exit):")

            # Run the query
            result = abstract_ai.query(query, self.collection_id)

            # print the result
            pretty_print_conversation(result)

            # if result.source_documents:
            #     source_docs = self.get_source_docs_to_print(
            #         result.source_documents
            #     )

            #     if len(source_docs) > 0:
            #         pretty_print_conversation("Source documents:\n" + source_docs, "blue")

    def get_multi_line_console_input(self):
        # Get the query, which can be multiple lines, until the user presses enter twice
        query = ""
        while True:
            line = input()
            if line == "":
                break
            query += line + "\n"

        return query
