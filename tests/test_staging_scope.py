import pytest
from fastapi.testclient import TestClient

from itlr.api.server import app


@pytest.mark.parametrize('path,body', [('/api/search', {'query': 'Docker'}),
                                        ('/api/chat', {'message': 'Xin chào'})])
def test_caller_cannot_switch_deployment_scope(path, body):
    client = TestClient(app)
    assert client.post(path, json=body, headers={'X-Tenant-ID': 'other'}).status_code == 400
    assert client.post(path, json={**body, 'tenant_id': 'other'}).status_code == 422


def test_paid_staging_requires_operator_opt_in_and_positive_shared_budget(monkeypatch, tmp_path):
    from itlr.chatbot import llm_client as llm

    secret = tmp_path / 'test_provider'
    secret.write_text('test-credential\n')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY_FILE', str(secret))
    monkeypatch.setenv('LLM_PROVIDER', 'openai')
    monkeypatch.setenv('ITLR_REQUIRE_CLOUD_AUTHORIZATION', '1')
    monkeypatch.setenv("ITLR_REDIS_URL", "redis://127.0.0.1:1/0")
    assert llm.api_key('openai') == 'test-credential'
    with pytest.raises(llm.LLMError, match='authorization'):
        llm.provider_status()
    monkeypatch.setenv('ITLR_CLOUD_AUTHORIZED', '1')
    monkeypatch.setenv('ITLR_LLM_MAX_RPM', '1')
    monkeypatch.setenv('ITLR_LLM_MAX_TPM', '0')
    with pytest.raises(llm.LLMError, match='authorization'):
        llm.provider_status()
    monkeypatch.setenv('ITLR_LLM_MAX_TPM', '4096')
    assert llm.provider_status() == 'openai'


def test_provider_error_reporting_survives_unavailable_secret(monkeypatch, tmp_path):
    from itlr.chatbot import llm_client as llm

    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setenv('DEEPSEEK_API_KEY_FILE', str(tmp_path / 'missing'))
    assert llm._safe_err_text(RuntimeError('provider error body')) == 'RuntimeError'
