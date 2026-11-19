from types import SimpleNamespace

import pytest

from itlr.chatbot import llm_client as lc, provider_budget


def test_open_circuit_refuses_provider_before_spending_quota(monkeypatch):
    class Redis:
        def get(self, key):
            assert key.endswith(':openai')
            return b'3'

    monkeypatch.setenv('ITLR_LLM_CIRCUIT_THRESHOLD', '3')
    monkeypatch.setattr(provider_budget, 'configured_redis', Redis)
    monkeypatch.setattr(lc, 'reserve_attempt', lambda *_: pytest.fail('reserved quota on open circuit'))
    with pytest.raises(lc.LLMError, match='circuit is open'):
        lc._reserve_attempt('openai', [], 20)


def test_model_routing_is_task_scoped_and_keeps_legacy_default(monkeypatch):
    monkeypatch.setenv('OPENAI_MODEL', 'legacy')
    monkeypatch.setenv('ITLR_OPENAI_EVIDENCE_MODEL', 'evidence-model')
    assert lc._completions_kwargs('openai', [], stream=False, temperature=0, max_tokens=10)['model'] == 'legacy'
    assert lc._completions_kwargs('openai', [], stream=False, temperature=0, max_tokens=10,
                                  output_schema={'type': 'array'})['model'] == 'evidence-model'


def test_retry_after_respects_budget_and_permanent_status():
    response = lambda delay: SimpleNamespace(headers={'Retry-After': delay})
    assert lc._retry_delay(SimpleNamespace(status_code=429, response=response('3')), .8) == 3
    assert lc._retry_delay(SimpleNamespace(status_code=429, response=response('60')), .8) is None
    assert lc._retry_delay(SimpleNamespace(status_code=401, response=response('3')), .8) is None
