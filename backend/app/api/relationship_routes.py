"""Confirmation APIs; no client SQL, inference or provider calls."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import CurrentUser
from app.auth.limits import resource_control
from app.core.config import get_settings
from app.core.errors import ConfigurationError, ResourceConflictError, ResourceNotFoundError
from app.database.session import get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput

router = APIRouter(prefix="/api/datasets/{dataset_id}/relationships")


def require_join_enabled() -> None:
    if not get_settings().sql_join_v1_enabled:
        raise HTTPException(403, "Liên kết bảng v1 hiện đang tắt.")


@contextmanager
def relationship_errors() -> Iterator[None]:
    try:
        yield
    except ResourceNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ResourceConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Chưa kiểm chứng được liên kết; hãy thử lại sau.") from exc


@router.get("")
def list_relationships(dataset_id: int, user: CurrentUser) -> dict:
    if not get_settings().sql_join_v1_enabled:
        return {"enabled": False, "relationships": []}
    with relationship_errors():
        items = RelationshipRepository(get_setup_engine(), user.user_id).list(dataset_id)
        return {"enabled": True, "relationships": [item.model_dump() for item in items]}


@router.post("/preview")
def preview_relationship(dataset_id: int, user: CurrentUser, request: RelationshipInput) -> dict:
    require_join_enabled()
    with relationship_errors(), resource_control().work(user.user_id, "preview"):
        return (
            RelationshipRepository(get_setup_engine(), user.user_id)
            .preview(
                dataset_id,
                request,
            )
            .model_dump()
        )


@router.post("/discover")
def discover_relationships(dataset_id: int, user: CurrentUser) -> dict:
    require_join_enabled()
    with relationship_errors(), resource_control().work(user.user_id, "preview"):
        return (
            RelationshipRepository(get_setup_engine(), user.user_id)
            .discover(dataset_id)
            .model_dump()
        )


@router.post("")
def confirm_relationship(dataset_id: int, user: CurrentUser, request: RelationshipConfirm) -> dict:
    require_join_enabled()
    with relationship_errors(), resource_control().work(user.user_id, "preview"):
        return (
            RelationshipRepository(get_setup_engine(), user.user_id)
            .confirm(
                dataset_id,
                request,
            )
            .model_dump()
        )


@router.delete("/{relationship_id}", status_code=204)
def delete_relationship(
    dataset_id: int,
    relationship_id: UUID,
    user: CurrentUser,
    confirmed: bool = Query(False),
) -> Response:
    require_join_enabled()
    if not confirmed:
        raise HTTPException(409, "Cần xác nhận xóa liên kết; dữ liệu hai bảng sẽ được giữ nguyên.")
    with relationship_errors():
        RelationshipRepository(get_setup_engine(), user.user_id).delete(dataset_id, relationship_id)
    return Response(status_code=204)
