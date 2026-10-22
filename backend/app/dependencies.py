"""Application object graph construction kept outside request handlers."""

from functools import partial
from uuid import UUID

from app.ai.chat import ModelChatService
from app.ai.gemini import GenerationGateway
from app.ai.providers import build_embedding_gateway
from app.conversations.repository import ConversationRepository
from app.core.config import Settings
from app.core.diagnostics import diagnostic_stage, record_facts
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.context import DatasetSqlContext, build_dataset_sql_context
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.repository import DatasetInfo, DatasetRepository
from app.rag.pipeline import RagPipeline
from app.rag.repository import DocumentRepository
from app.rag.reranker import build_reranker
from app.routing.hybrid import HybridPipeline
from app.routing.router import QueryRouter
from app.routing.service import ChatService, DatasetChatService
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.generator import SqlGenerator
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import SqlValidator


def build_chat_service(settings: Settings) -> ModelChatService:
    return ModelChatService(settings, lambda gateway: _build_chat_service(settings, gateway))


def _build_chat_service(settings: Settings, gateway: GenerationGateway) -> ChatService:
    """Create request-safe stateless pipelines around shared connection pools."""

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
        embedder=build_embedding_gateway(settings),
        gateway=gateway,
        repository=DocumentRepository(get_setup_engine(), readonly_engine),
        reranker=build_reranker(settings),
        candidate_top_k=settings.rag_candidate_top_k,
        top_n=settings.rag_top_n,
    )
    return ChatService(
        router=QueryRouter(gateway),
        sql_pipeline=sql_pipeline,
        rag_pipeline=rag_pipeline,
        hybrid_pipeline=HybridPipeline(sql_pipeline, rag_pipeline, gateway),
    )


def build_dataset_chat_service(
    settings: Settings, context: DatasetSqlContext
) -> ModelChatService | DatasetChatService:
    if not context.table_columns and not context.has_documents:
        return DatasetChatService(None, None, None, None, settings.ai_default_model)
    return ModelChatService(
        settings, lambda gateway: _build_dataset_chat_service(settings, context, gateway)
    )


@diagnostic_stage("schema_metadata")
def build_workspace_context(
    settings: Settings,
    dataset: DatasetInfo,
    repository: DatasetRepository,
) -> DatasetSqlContext:
    joins = ()
    if settings.sql_join_v1_enabled:
        with diagnostic_stage("relationship_approval"):
            joins = RelationshipRepository(get_setup_engine(), dataset.owner_user_id).approved(
                dataset.dataset_id
            )
    return build_dataset_sql_context(
        dataset,
        repository.categorical_values(dataset),
        approved_joins=joins,
        join_v1_enabled=settings.sql_join_v1_enabled,
    )


def _build_dataset_chat_service(
    settings: Settings, context: DatasetSqlContext, gateway: GenerationGateway
) -> DatasetChatService:
    """Build request-local pipelines scoped to one uploaded workspace."""

    record_facts(
        allowed_tables=len(context.table_columns), approved_edges=len(context.approved_joins)
    )

    sql_pipeline = None
    joins = context.approved_joins if settings.sql_join_v1_enabled else ()
    if context.table_columns:
        sql_pipeline = TextToSqlPipeline(
            generator=SqlGenerator(
                gateway,
                settings.demo_reference_date,
                schema_context=context.schema_context,
            ),
            validator=SqlValidator(
                table_columns=context.table_columns,
                allowed_schemas=context.allowed_schemas,
                max_tables=3 if len(joins) >= 2 else 2 if joins else 1,
                approved_joins=joins,
                column_types=context.column_types,
                join_v1_enabled=settings.sql_join_v1_enabled,
            ),
            executor=SqlExecutor(
                get_readonly_engine(),
                settings.sql_statement_timeout_ms,
                settings.sql_max_rows,
            ),
            gateway=gateway,
            execution_guard=partial(
                RelationshipRepository(get_setup_engine(), context.owner_user_id).execution_guard,
                context.dataset_id,
                joins,
            )
            if joins
            else None,
        )
    rag_pipeline = None
    if context.has_documents:
        rag_pipeline = RagPipeline(
            embedder=build_embedding_gateway(settings),
            gateway=gateway,
            repository=DocumentRepository(
                get_setup_engine(), get_readonly_engine(), context.owner_user_id
            ),
            dataset_id=context.dataset_id,
            reranker=build_reranker(settings),
            candidate_top_k=settings.rag_candidate_top_k,
            top_n=settings.rag_top_n,
        )
    hybrid_pipeline = (
        HybridPipeline(sql_pipeline, rag_pipeline, gateway, context)
        if sql_pipeline is not None and rag_pipeline is not None
        else None
    )
    return DatasetChatService(
        QueryRouter(gateway, source_context=context.routing_context or context.schema_context),
        sql_pipeline,
        rag_pipeline,
        hybrid_pipeline,
    )


def build_document_repository(owner_user_id: UUID) -> DocumentRepository:
    return DocumentRepository(get_setup_engine(), get_readonly_engine(), owner_user_id)


def build_dataset_repository(owner_user_id: UUID) -> DatasetRepository:
    return DatasetRepository(get_setup_engine(), get_readonly_engine(), owner_user_id)


def build_conversation_repository(owner_user_id: UUID) -> ConversationRepository:
    return ConversationRepository(get_setup_engine(), owner_user_id)
