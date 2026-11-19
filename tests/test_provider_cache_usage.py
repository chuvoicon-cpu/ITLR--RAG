from types import SimpleNamespace

from itlr.chatbot import llm_client as lc


def test_prompt_cache_metadata_distinguishes_missing_and_zero():
    assert lc.prompt_cache_usage('openai', SimpleNamespace(prompt_tokens=100)) == (None, None)
    assert lc.prompt_cache_usage('openai', SimpleNamespace(
        prompt_tokens=100, prompt_tokens_details=SimpleNamespace(cached_tokens=0))) == (0, 100)
    assert lc.prompt_cache_usage('deepseek', SimpleNamespace(
        prompt_tokens=100, prompt_cache_hit_tokens=80, prompt_cache_miss_tokens=20)) == (80, 20)
    assert lc.prompt_cache_usage('deepseek', SimpleNamespace(
        prompt_tokens=100, prompt_cache_hit_tokens=80, prompt_cache_miss_tokens=40)) == (None, None)
    assert lc.prompt_cache_usage('ollama', SimpleNamespace(prompt_tokens=100, cached_tokens=100)) == (None, None)


def test_explicit_provider_does_not_fallback(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'openai')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert lc.provider_status() == 'none'
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    assert lc.provider_status() == 'openai'


def test_usage_aggregates_only_real_metadata(monkeypatch):
    lc.reset_cache()
    monkeypatch.setenv('ITLR_LLM_PRICE_JSON', '{"deepseek/test":{"input":1,"cached":0.1,"output":2}}')
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=5,
                            prompt_cache_hit_tokens=80, prompt_cache_miss_tokens=20)
    cached, uncached, cost, saving = lc.record_provider_usage('deepseek', 'test', usage)
    assert (cached, uncached, cost, saving) == (80, 20, .000038, .000072)
    assert lc.record_provider_usage('deepseek', 'test', None) == (None, None, None, None)
    state = lc.usage_snapshot()['by_provider']['deepseek']
    assert state['cache_observed_calls'] == 1
    assert state['cache_metadata_missing_calls'] == 1
    assert state['cached_input_tokens'] == 80
    lc.reset_cache()
