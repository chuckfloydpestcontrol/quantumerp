"""
Conversation Service - Manages chat history and context.

Provides conversation memory for the Quantum HUB, enabling
context-aware responses across multiple messages.
"""

from datetime import datetime
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from models import ChatMessage, ConversationState, MessageRole


class ConversationService:
    """Service for managing conversation history and state."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_history(
        self,
        thread_id: str,
        limit: int = 20
    ) -> list[BaseMessage]:
        """
        Get conversation history as LangChain messages.

        Args:
            thread_id: Conversation thread ID
            limit: Maximum messages to retrieve

        Returns:
            List of LangChain message objects
        """
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(desc(ChatMessage.created_at))
            .limit(limit)
        )
        db_messages = list(reversed(result.scalars().all()))

        messages = []
        for msg in db_messages:
            if msg.role == MessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            else:
                messages.append(AIMessage(content=msg.content))

        return messages

    async def get_last_response_data(
        self,
        thread_id: str
    ) -> Optional[dict]:
        """
        Get the response_data from the last assistant message.

        Useful for follow-up actions like quote acceptance.
        """
        result = await self.db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.role == MessageRole.ASSISTANT
            )
            .order_by(desc(ChatMessage.created_at))
            .limit(1)
        )
        last_msg = result.scalar_one_or_none()

        if last_msg and last_msg.response_data:
            return last_msg.response_data
        return None

    async def get_or_create_state(
        self,
        thread_id: str
    ) -> ConversationState:
        """Get or create conversation state for a thread."""
        result = await self.db.execute(
            select(ConversationState)
            .where(ConversationState.thread_id == thread_id)
        )
        state = result.scalar_one_or_none()

        if not state:
            state = ConversationState(
                thread_id=thread_id,
                checkpoint={"node": "start"},
                extra_data={}
            )
            self.db.add(state)
            await self.db.flush()

        return state

    async def update_state(
        self,
        thread_id: str,
        current_node: str,
        state_data: dict
    ) -> ConversationState:
        """Update conversation state."""
        state = await self.get_or_create_state(thread_id)
        state.checkpoint = {"node": current_node}
        state.extra_data = {**(state.extra_data or {}), **state_data}
        state.updated_at = datetime.utcnow()
        await self.db.flush()
        return state

    async def store_pending_quote(
        self,
        thread_id: str,
        quote_options: dict,
        customer_name: str,
        product_description: str
    ) -> None:
        """Store quote options for later acceptance."""
        await self.update_state(
            thread_id=thread_id,
            current_node="awaiting_quote_selection",
            state_data={
                "pending_quote": quote_options,
                "customer_name": customer_name,
                "product_description": product_description
            }
        )

    async def get_pending_quote(
        self,
        thread_id: str
    ) -> Optional[dict]:
        """Get pending quote options if any."""
        state = await self.get_or_create_state(thread_id)
        if state.extra_data and "pending_quote" in state.extra_data:
            return state.extra_data
        return None

    async def clear_pending_quote(self, thread_id: str) -> None:
        """Clear pending quote after acceptance."""
        state = await self.get_or_create_state(thread_id)
        if state.extra_data:
            state.extra_data.pop("pending_quote", None)
            state.checkpoint = {"node": "idle"}
            await self.db.flush()
