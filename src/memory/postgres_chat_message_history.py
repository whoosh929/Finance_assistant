from typing import List
from uuid import UUID

from langchain.schema.memory import BaseChatMessageHistory
from langchain.schema.messages import BaseMessage
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage, FunctionMessage

from db.models.conversations import Conversations, ConversationModel
from db.models.domain.conversation_role_type import ConversationRoleType

class PostgresChatMessageHistory(BaseChatMessageHistory):
    """Chat message history stored in Postgres."""

    interaction_id: UUID
    conversations: Conversations
    user_id: int

    def __init__(self, interaction_id: UUID, conversations: Conversations, max_token_limit: int = 500):
        """Initialize the PostgresChatMessageHistory.

        Args:
            interaction_id: The ID of the interaction to store messages for.
            conversations: The Conversations object to use for storing messages.
        """
        self.interaction_id = interaction_id
        self.conversations = conversations
        self.max_token_limit = max_token_limit

    @property
    def messages(self) -> List[BaseMessage]:
        """A list of Messages stored in the DB."""
        #return self.chat_messages    
        chat_messages = []       
        messages = self.conversations.get_conversations_for_interaction(
            self.interaction_id
        )
        for message in messages:
            if message.conversation_role_type == ConversationRoleType.USER:
                chat_messages.append(
                    HumanMessage(content=message.conversation_text)
                )
            elif message.conversation_role_type == ConversationRoleType.ASSISTANT:
                chat_messages.append(AIMessage(content=message.conversation_text))
            elif message.conversation_role_type == ConversationRoleType.SYSTEM:
                chat_messages.append(
                    SystemMessage(content=message.conversation_text)
                )

        return chat_messages

    def add_message(self, message: BaseMessage) -> None:
        """Add a Message object to the store.

        Args:
            message: A BaseMessage object to store.
        """

        if type(message) == HumanMessage:            
            role_type = ConversationRoleType.USER
        elif type(message) == AIMessage:
            role_type = ConversationRoleType.ASSISTANT
        elif type(message) == SystemMessage:
            role_type = ConversationRoleType.SYSTEM
        elif type(message) == FunctionMessage:
            role_type = ConversationRoleType.FUNCTION
        else:
            raise ValueError("Unknown message type")

        self.conversations.add_conversation(ConversationModel(            
            interaction_id=self.interaction_id,
            conversation_text=message.content,
            conversation_role_type=role_type,
            user_id=self.user_id,
        ))

        #self.chat_messages.append(message)

    def clear(self) -> None:
        """Clear memory contents."""
        raise NotImplementedError(
            "clear() not implemented for PostgresChatMessageHistory"
        )