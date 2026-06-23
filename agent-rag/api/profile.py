from __future__ import annotations

from fastapi import APIRouter, Request

from api.schemas import TenantProfileResponse, TenantProfileUpdateRequest
from api.tenant_profile_service import (
    get_tenant_profile_response,
    put_tenant_profile_response,
    resolve_tenant_id,
)

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile", response_model=TenantProfileResponse)
def get_profile(request: Request) -> TenantProfileResponse:
    tenant_id = resolve_tenant_id(request)
    return get_tenant_profile_response(tenant_id)


@router.put("/profile", response_model=TenantProfileResponse)
def put_profile(
    request: Request,
    body: TenantProfileUpdateRequest,
) -> TenantProfileResponse:
    tenant_id = resolve_tenant_id(request)
    return put_tenant_profile_response(tenant_id, body)
