from typing import Union, List, Any
from uuid import UUID
from sqlalchemy.orm.attributes import InstrumentedAttribute

from src.db.database.models import Conversation
from src.db.models.vector_database import VectorDatabase, SearchType

from src.db.models.domain.conversation_model import ConversationModel


class Conversations(VectorDatabase):
    def add_conversation(self, conversation: ConversationModel) -> ConversationModel:
        with self.session_context(self.Session()) as session:
            conversation.conversation_text = conversation.conversation_text.strip()

            if len(conversation.conversation_text) == 0:
                return

            db_conversation = conversation.to_database_model()
            db_conversation.embedding = self.get_embedding(
                conversation.conversation_text
            )

            session.add(db_conversation)
            session.commit()

            return ConversationModel.from_database_model(db_conversation)

    def delete_conversation(self, conversation_id: int) -> None:
        with self.session_context(self.Session()) as session:
            session.query(Conversation).filter(
                Conversation.id == conversation_id
            ).update({Conversation.is_deleted: True})
            session.commit()

    def delete_conversation_by_interaction_id(self, interaction_id: UUID) -> None:
        with self.session_context(self.Session()) as session:
            session.query(Conversation).filter(
                Conversation.interaction_id == interaction_id
            ).update({Conversation.is_deleted: True})
            session.commit()

    def search_conversations_with_user_id(
        self,
        search_query: str,
        search_type: SearchType,
        associated_user_id: int,
        interaction_id: Union[UUID, None] = None,
        top_k=10,
        return_deleted=False,
    ) -> List[ConversationModel]:
        # TODO: Handle searching metadata... e.g. metadata_search_query: Union[str,None] = None

        with self.session_context(self.Session()) as session:
            # Before searching, pre-filter the query to only include conversations that match the single inputs
            query = session.query(Conversation).filter(
                Conversation.is_deleted == return_deleted,
                Conversation.user_id == associated_user_id,
                Conversation.interaction_id == interaction_id
                if interaction_id is not None
                else True,
            )

            if type(search_type) == str:
                search_type = SearchType(search_type)

            if search_type == SearchType.Keyword:
                # TODO: Do better key word search
                query = query.filter(
                    Conversation.conversation_text.contains(search_query)
                ).limit(top_k)
            elif search_type == SearchType.Similarity:
                # Calculate the query embedding, then search for the nearest neighbors
                embedding = self.get_embedding(search_query)
                query = self._get_nearest_neighbors(
                    session, query, embedding, top_k=top_k
                )
            else:
                raise ValueError(f"Unknown search type: {search_type}")

            return [ConversationModel.from_database_model(c) for c in query]

    def get_conversations_for_interaction(
        self, interaction_id: UUID, top_k: int = None, return_deleted=None
    ) -> List[ConversationModel]:
        if return_deleted is None:
            return_deleted = False
        elif return_deleted is True:
            return_deleted = True

        with self.session_context(self.Session()) as session:
            query = (
                session.query(
                    Conversation.interaction_id,
                    Conversation.conversation_text,
                    Conversation.user_id,
                    Conversation.id,
                    Conversation.record_created,
                    Conversation.conversation_role_type_id,
                    Conversation.additional_metadata,
                    Conversation.exception,
                    Conversation.is_deleted,
                )
                .filter(
                    Conversation.interaction_id == interaction_id,
                    (Conversation.is_deleted == False)
                    if return_deleted == False
                    else True,
                )
                .order_by(Conversation.record_created)
            )

            #query = super().eager_load(query, [Conversation.conversation_role_type])

            return [
                ConversationModel.from_database_model(c) for c in query.limit(top_k)
            ]

    def get_conversations_for_user(
        self, associated_user_id: int, top_k: int = None
    ) -> List[ConversationModel]:
        with self.session_context(self.Session()) as session:
            query = session.query(
                Conversation.interaction_id,
                Conversation.conversation_text,
                Conversation.user_id,
                Conversation.conversation_role_type,
                Conversation.id,
                Conversation.record_created,
                Conversation.additional_metadata,
                Conversation.exception,
                Conversation.is_deleted,
            ).filter(Conversation.user_id == associated_user_id)

            query = super().eager_load(query, [Conversation.conversation_role_type])

            query = query.order_by(Conversation.record_created).all()

            return [
                ConversationModel.from_database_model(c) for c in query.limit(top_k)
            ]

    def _get_nearest_neighbors(self, session, query, embedding, top_k=5):
        return session.scalars(
            query.order_by(Conversation.embedding.l2_distance(embedding)).limit(top_k)
        )
