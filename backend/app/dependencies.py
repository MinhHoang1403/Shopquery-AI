"""Application object graph construction kept outside request handlers."""

from functools import lru_cache
from threading import Lock

from app.ai.gemini import GeminiGateway
from app.conversations.repository import ConversationRepository
from app.core.config import Settings
from app.database.session import get_readonly_engine, get_setup_engine
from app.database.setup import create_schema
from app.datasets.context import DatasetSqlContext
from app.datasets.repository import DatasetRepository
from app.rag.pipeline import RagPipeline
from app.rag.repository import DocumentRepository
from app.routing.hybrid import HybridPipeline
from app.routing.router import QueryRouter
from app.routing.service import ChatService, DatasetChatService
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.generator import SqlGenerator
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import SqlValidator

_schema_setup_lock = Lock()


def build_chat_service(settings: Settings) -> ChatService:
    """Create request-safe stateless pipelines around shared connection pools."""

    gateway = GeminiGateway(settings)
    readonly_engine = get_readonly_engine()
    sql_pipeline = TextToSqlPipeline(
        generator=SqlGenerator(gateway, settings.demo_reference_date),
        validator=SqlValidator(),
        executor=SqlExecutor(
            readonly_engine,
            settings.sql_statement_timeout_ms,
            settings.sql_max_rows,
        ),
        gateway=gateway,
    )
    rag_pipeline = RagPipeline(
        embedder=gateway,
        gateway=gateway,
        repository=DocumentRepository(get_setup_engine(), readonly_engine),
    )
    return ChatService(
        router=QueryRouter(gateway),
        sql_pipeline=sql_pipeline,
        rag_pipeline=rag_pipeline,
        hybrid_pipeline=HybridPipeline(sql_pipeline, rag_pipeline, gateway),
    )


def build_dataset_chat_service(
    settings: Settings, context: DatasetSqlContext
) -> DatasetChatService:
    """Build an SQL-only pipeline scoped to one uploaded dataset."""

    gateway = GeminiGateway(settings)
    sql_pipeline = TextToSqlPipeline(
        generator=SqlGenerator(
            gateway,
            settings.demo_reference_date,
            schema_context=context.schema_context,
        ),
        validator=SqlValidator(
            table_columns=context.table_columns,
            allowed_schemas=context.allowed_schemas,
        ),
        executor=SqlExecutor(
            get_readonly_engine(),
            settings.sql_statement_timeout_ms,
            settings.sql_max_rows,
        ),
        gateway=gateway,
    )
    return DatasetChatService(sql_pipeline)


def build_dataset_repository() -> DatasetRepository:
    ensure_application_schema(get_settings_url())
    return DatasetRepository(get_setup_engine(), get_readonly_engine())


def build_conversation_repository() -> ConversationRepository:
    ensure_application_schema(get_settings_url())
    return ConversationRepository(get_setup_engine())


def get_settings_url() -> str:
    """Return the active setup URL without exposing it in logs or responses."""

    from app.core.config import get_settings

    return get_settings().database_setup_url


@lru_cache
def ensure_application_schema(database_url: str) -> None:
    """Serialize idempotent schema setup for each cached database URL."""

    del database_url
    with _schema_setup_lock:
        create_schema(get_setup_engine())
