"""Transactional PostgreSQL repository for conversations and messages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, selectinload

from app.ai.providers import MODEL_LABELS
from app.core.errors import ResourceNotFoundError
from app.database.models import ChatConversation, ChatMessage, Dataset

DEFAULT_TITLE = "Cuộc trò chuyện mới"


@dataclass(frozen=True)
class MessageRecord:
    message_id: int
    role: str
    content: str
    response_metadata: dict[str, Any] | None
    created_at: datetime


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: UUID
    title: str
    dataset_id: int | None
    dataset_name: str
    created_at: datetime
    updated_at: datetime
    messages: tuple[MessageRecord, ...] = ()
    model_id: str = "gemini"
    owner_user_id: UUID | None = None


class ConversationRepository:
    def __init__(self, engine: Engine, owner_user_id: UUID) -> None:
        if not isinstance(owner_user_id, UUID):
            raise ValueError("An authenticated owner is required")
        self._engine = engine
        self._owner_user_id = owner_user_id

    def list(self, limit: int, offset: int) -> list[ConversationRecord]:
        statement = (
            select(ChatConversation)
            .where(ChatConversation.owner_user_id == self._owner_user_id)
            .options(selectinload(ChatConversation.dataset))
            .order_by(ChatConversation.updated_at.desc(), ChatConversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with Session(self._engine) as session:
            conversations = session.scalars(statement).all()
            return [self._to_record(conversation) for conversation in conversations]

    def create(
        self, dataset_id: int | None, model_id: str = "inetcloud-knowledge"
    ) -> ConversationRecord:
        if model_id not in MODEL_LABELS:
            raise ValueError("Mô hình AI không được hỗ trợ.")
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            dataset = None
            if dataset_id is not None:
                dataset = session.scalar(
                    select(Dataset)
                    .where(
                        Dataset.dataset_id == dataset_id,
                        Dataset.owner_user_id == self._owner_user_id,
                    )
                    .with_for_update()
                )
                if dataset is None:
                    raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")
            conversation = ChatConversation(
                dataset_id=dataset_id, model_id=model_id, owner_user_id=self._owner_user_id
            )
            session.add(conversation)
            session.flush()
            conversation.dataset = dataset
            return self._to_record(conversation)

    def get(self, conversation_id: UUID) -> ConversationRecord:
        statement = (
            select(ChatConversation)
            .options(
                selectinload(ChatConversation.dataset),
                selectinload(ChatConversation.messages),
            )
            .where(
                ChatConversation.conversation_id == conversation_id,
                ChatConversation.owner_user_id == self._owner_user_id,
            )
        )
        with Session(self._engine) as session:
            conversation = session.scalar(statement)
            if conversation is None:
                raise ResourceNotFoundError("Không tìm thấy cuộc trò chuyện.")
            return self._to_record(conversation, include_messages=True)

    def rename(self, conversation_id: UUID, title: str) -> ConversationRecord:
        normalized_title = " ".join(title.split())
        if not normalized_title:
            raise ValueError("Tên cuộc trò chuyện không được để trống.")
        if len(normalized_title) > 120:
            raise ValueError("Tên cuộc trò chuyện không được vượt quá 120 ký tự.")
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            conversation = session.scalar(
                select(ChatConversation)
                .where(
                    ChatConversation.conversation_id == conversation_id,
                    ChatConversation.owner_user_id == self._owner_user_id,
                )
                .with_for_update()
            )
            if conversation is None:
                raise ResourceNotFoundError("Không tìm thấy cuộc trò chuyện.")
            conversation.title = normalized_title
            conversation.title_customized = True
            conversation.updated_at = datetime.now(UTC)
        return self.get(conversation_id)

    def delete(self, conversation_id: UUID) -> None:
        with Session(self._engine) as session, session.begin():
            conversation = session.scalar(
                select(ChatConversation)
                .where(
                    ChatConversation.conversation_id == conversation_id,
                    ChatConversation.owner_user_id == self._owner_user_id,
                )
                .with_for_update()
            )
            if conversation is None:
                raise ResourceNotFoundError("Không tìm thấy cuộc trò chuyện.")
            session.delete(conversation)

    def set_model(self, conversation_id: UUID, model_id: str) -> ConversationRecord:
        if model_id not in MODEL_LABELS:
            raise ValueError("Mô hình AI không được hỗ trợ.")
        with Session(self._engine) as session, session.begin():
            conversation = session.scalar(
                select(ChatConversation)
                .where(
                    ChatConversation.conversation_id == conversation_id,
                    ChatConversation.owner_user_id == self._owner_user_id,
                )
                .with_for_update()
            )
            if conversation is None:
                raise ResourceNotFoundError("Không tìm thấy cuộc trò chuyện.")
            conversation.model_id = model_id
            conversation.updated_at = datetime.now(UTC)
        return self.get(conversation_id)

    def add_user_message(self, conversation_id: UUID, content: str) -> MessageRecord:
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            conversation = session.scalar(
                select(ChatConversation)
                .where(
                    ChatConversation.conversation_id == conversation_id,
                    ChatConversation.owner_user_id == self._owner_user_id,
                )
                .with_for_update()
            )
            if conversation is None:
                raise ResourceNotFoundError("Không tìm thấy cuộc trò chuyện.")
            user_count = session.scalar(
                select(func.count(ChatMessage.message_id)).where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.role == "user",
                )
            )
            if not conversation.title_customized and user_count == 0:
                conversation.title = _title_from_question(content)
            conversation.updated_at = datetime.now(UTC)
            message = ChatMessage(
                conversation_id=conversation_id,
                role="user",
                content=content,
            )
            session.add(message)
            session.flush()
            return self._message_record(message)

    def add_response_message(
        self,
        conversation_id: UUID,
        *,
        content: str,
        response_metadata: dict[str, Any],
        is_error: bool,
    ) -> MessageRecord:
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            conversation = session.scalar(
                select(ChatConversation)
                .where(
                    ChatConversation.conversation_id == conversation_id,
                    ChatConversation.owner_user_id == self._owner_user_id,
                )
                .with_for_update()
            )
            if conversation is None:
                raise ResourceNotFoundError("Không tìm thấy cuộc trò chuyện.")
            conversation.updated_at = datetime.now(UTC)
            message = ChatMessage(
                conversation_id=conversation_id,
                role="error" if is_error else "assistant",
                content=content,
                response_metadata=response_metadata,
            )
            session.add(message)
            session.flush()
            return self._message_record(message)

    @staticmethod
    def _to_record(
        conversation: ChatConversation, *, include_messages: bool = False
    ) -> ConversationRecord:
        return ConversationRecord(
            conversation_id=conversation.conversation_id,
            title=conversation.title,
            dataset_id=conversation.dataset_id,
            dataset_name=(
                conversation.dataset.name if conversation.dataset else "Dữ liệu cửa hàng mẫu"
            ),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            model_id=conversation.model_id or "gemini",
            owner_user_id=conversation.owner_user_id,
            messages=(
                tuple(
                    ConversationRepository._message_record(message)
                    for message in conversation.messages
                )
                if include_messages
                else ()
            ),
        )

    @staticmethod
    def _message_record(message: ChatMessage) -> MessageRecord:
        return MessageRecord(
            message_id=message.message_id,
            role=message.role,
            content=message.content,
            response_metadata=message.response_metadata,
            created_at=message.created_at,
        )


def _title_from_question(question: str) -> str:
    compact = " ".join(question.split())
    if len(compact) <= 56:
        return compact
    return f"{compact[:55].rstrip()}…"
