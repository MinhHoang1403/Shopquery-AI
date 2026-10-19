"""RAM-only confirmation with the existing capability, quotas and isolated worker."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.relationship_routes import require_join_enabled
from app.core.config import get_settings
from app.datasets.relationships import RelationshipConfirm, RelationshipInput, RelationshipRecord
from app.guest.routes import CurrentGuest, guest_control, peer_ip
from app.guest.store import GuestContext, guest_store
from app.guest.worker import run_isolated

router = APIRouter(prefix="/api/guest/relationships")


@router.get("")
def list_relationships(guest: CurrentGuest) -> dict:
    with guest_store().operation(guest):
        enabled = get_settings().sql_join_v1_enabled
        return {
            "enabled": enabled,
            "relationships": [r.model_dump() for r in guest.relationships] if enabled else [],
        }


def check_relationship(request: Request, guest: GuestContext, body: RelationshipInput) -> dict:
    require_join_enabled()
    settings, store, control = get_settings(), guest_store(), guest_control()
    control.ip_rate(peer_ip(request), "preview", settings.guest_previews_per_ip_hour)
    with store.operation(guest), control.lease(guest.key, settings):
        if guest.parse_count >= settings.guest_previews_per_session:
            raise HTTPException(429, "Đã hết lượt kiểm tra dữ liệu của phiên khách.")
        guest.parse_count += 1
        preview = run_isolated("relationship", (list(guest.files), body), settings, guest.cancelled)
        store.ensure_active(guest)
        if isinstance(body, RelationshipConfirm):
            if body.revision != preview.revision:
                raise HTTPException(409, "Tệp đã thay đổi; hãy kiểm tra liên kết lại.")
            if not preview.valid:
                raise HTTPException(409, " ".join(preview.reasons))
            return store.confirm_relationship(
                guest,
                RelationshipRecord(
                    **preview.model_dump(),
                    relationship_id=uuid4().hex,
                ),
            ).model_dump()
        return preview.model_dump()


@router.post("/preview")
def preview_relationship(request: Request, guest: CurrentGuest, body: RelationshipInput) -> dict:
    return check_relationship(request, guest, body)


@router.post("")
def confirm_relationship(request: Request, guest: CurrentGuest, body: RelationshipConfirm) -> dict:
    return check_relationship(request, guest, body)


@router.delete("/{relationship_id}", status_code=204)
def delete_relationship(
    relationship_id: str, guest: CurrentGuest, confirmed: bool = Query(False)
) -> Response:
    require_join_enabled()
    with guest_store().operation(guest):
        if not confirmed:
            raise HTTPException(409, "Cần xác nhận xóa liên kết. Các tệp vẫn được giữ nguyên.")
        guest_store().delete_relationship(guest, relationship_id)
    return Response(status_code=204)
