import pytest
from fastapi import HTTPException
from services.authorization_service import AuthContext, verify_scope, validate_resource_access

def test_auth_context_and_verify_scope():
    ctx = AuthContext(
        application_id="1",
        api_key_id="10",
        user_id="100",
        scopes=["agent:invoke", "agent:read"],
        app_default_scopes=["agent:invoke"],
    )
    # Should not raise
    verify_scope(ctx, "agent:invoke")
    verify_scope(ctx, "agent:read")

    # Missing scope should raise 403
    with pytest.raises(HTTPException) as exc_info:
        verify_scope(ctx, "agent:write")
    assert exc_info.value.status_code == 403

def test_verify_scope_wildcard():
    ctx = AuthContext(
        application_id="1",
        api_key_id="10",
        user_id="100",
        scopes=["*"],
        app_default_scopes=[],
    )
    # Wildcard should allow anything
    verify_scope(ctx, "agent:invoke")
    verify_scope(ctx, "agent:delete")

@pytest.mark.asyncio
async def test_validate_resource_access_skills_gate():
    # Attempting skill_ids without a claude model/provider should raise 400
    with pytest.raises(HTTPException) as exc_info:
        await validate_resource_access(
            user_id="100",
            skill_ids=["sk_1"],
            model_id="gpt-4o",
            provider_id=None,
        )
    assert exc_info.value.status_code == 400
    assert "Skills (skill_ids) are restricted to Claude models" in exc_info.value.detail

    # Allowed when model_id has 'claude'
    res = await validate_resource_access(
        user_id="100",
        skill_ids=["sk_1"],
        model_id="claude-3-5-sonnet",
        provider_id=None,
    )
    assert res is None
