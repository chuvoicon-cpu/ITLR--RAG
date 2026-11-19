import pytest

from itlr.chatbot import provider_budget


def test_configured_provider_quota_fails_closed_and_uses_safe_reservation(monkeypatch):
    monkeypatch.setenv('ITLR_LLM_MAX_RPM', '2')
    monkeypatch.setenv('ITLR_LLM_MAX_TPM', '1000')
    monkeypatch.setattr(provider_budget, 'configured_redis', lambda: None)
    with pytest.raises(provider_budget.ProviderBudgetError, match='unavailable'):
        provider_budget.reserve_attempt('openai', [], 10)

    class Redis:
        def eval(self, script, key_count, key, rpm, tpm, reserved):
            assert key.endswith(':openai')
            assert (key_count, rpm, tpm, reserved) == (1, 2, 1000, 61)
            return 0

    monkeypatch.setattr(provider_budget, 'configured_redis', Redis)
    with pytest.raises(provider_budget.ProviderBudgetError, match='exhausted'):
        provider_budget.reserve_attempt('openai', [{'role': 'user', 'content': 'có'}], 10)
