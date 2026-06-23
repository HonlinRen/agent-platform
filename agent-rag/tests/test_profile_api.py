from __future__ import annotations

from unittest.mock import MagicMock, patch

from api.schemas import TenantProfileData, TenantProfileUpdateRequest
from api.tenant_profile_service import get_tenant_profile_response, put_tenant_profile_response


@patch("api.tenant_profile_service.get_db")
def test_get_tenant_profile_response_empty(mock_get_db):
    session = MagicMock()
    mock_get_db.return_value.__enter__.return_value = session
    session_repo = MagicMock()
    session_repo.get_tenant_profile.return_value = None
    with patch("api.tenant_profile_service.ConversationRepository", return_value=session_repo):
        result = get_tenant_profile_response("tenant_a")

    assert result.tenant_id == "tenant_a"
    assert result.profile == TenantProfileData()
    assert result.profile_summary is None
    assert result.source == "auto"


@patch("api.tenant_profile_service.get_db")
def test_put_tenant_profile_response_manual(mock_get_db):
    session = MagicMock()
    mock_get_db.return_value.__enter__.return_value = session
    row = MagicMock()
    row.profile_summary = "关注领域：半导体"
    row.updated_at = None
    session_repo = MagicMock()
    session_repo.get_tenant_profile.return_value = row
    with patch("api.tenant_profile_service.ConversationRepository", return_value=session_repo):
        body = TenantProfileUpdateRequest(
            profile=TenantProfileData(
                focus_domains=["半导体"],
                preferred_answer_style="简洁",
                common_systems=["MES"],
                notes="测试",
            )
        )
        result = put_tenant_profile_response("tenant_a", body)

    session_repo.upsert_tenant_profile.assert_called_once()
    assert result.source == "manual"
    assert result.profile.focus_domains == ["半导体"]
