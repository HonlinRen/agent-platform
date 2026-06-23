from __future__ import annotations

from fastapi import Request

from api.schemas import TenantProfileData, TenantProfileResponse, TenantProfileUpdateRequest
from db.repository import ConversationRepository
from db.session import get_db
from rag.memory.tenant_profile import DEFAULT_PROFILE, profile_to_summary


def resolve_tenant_id(request: Request) -> str:
    return request.headers.get("X-Tenant-Id") or "default_tenant"


def get_tenant_profile_response(tenant_id: str) -> TenantProfileResponse:
    with get_db() as session:
        row = ConversationRepository(session).get_tenant_profile(tenant_id)
        if row is None:
            return TenantProfileResponse(
                tenant_id=tenant_id,
                profile=TenantProfileData(**DEFAULT_PROFILE),
                profile_summary=None,
                source="auto",
                updated_at=None,
            )
        profile_data = row.profile_json if isinstance(row.profile_json, dict) else DEFAULT_PROFILE
        return TenantProfileResponse(
            tenant_id=tenant_id,
            profile=TenantProfileData(
                focus_domains=profile_data.get("focus_domains") or [],
                preferred_answer_style=profile_data.get("preferred_answer_style") or "",
                common_systems=profile_data.get("common_systems") or [],
                notes=profile_data.get("notes") or "",
            ),
            profile_summary=row.profile_summary,
            source=row.source,  # type: ignore[arg-type]
            updated_at=row.updated_at,
        )


def put_tenant_profile_response(
    tenant_id: str,
    body: TenantProfileUpdateRequest,
) -> TenantProfileResponse:
    profile_json = body.profile.model_dump()
    summary = body.profile_summary or profile_to_summary(profile_json)
    with get_db() as session:
        ConversationRepository(session).upsert_tenant_profile(
            tenant_id,
            profile_json,
            summary,
            source="manual",
        )
        row = ConversationRepository(session).get_tenant_profile(tenant_id)
        assert row is not None
        return TenantProfileResponse(
            tenant_id=tenant_id,
            profile=body.profile,
            profile_summary=row.profile_summary,
            source="manual",
            updated_at=row.updated_at,
        )
