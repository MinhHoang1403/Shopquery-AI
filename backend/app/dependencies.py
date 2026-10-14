"""Application object graph construction kept outside request handlers."""

from app.ai.gemini import GeminiGateway
from app.core.config import Settings
from app.database.session import get_readonly_engine, get_setup_engine
from app.rag.pipeline import RagPipeline
from app.rag.repository import DocumentRepository
from app.routing.hybrid import HybridPipeline
from app.routing.router import QueryRouter
from app.routing.service import ChatService
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.generator import SqlGenerator
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import SqlValidator


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
