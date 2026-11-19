"""Optional global admission for provider attempts, shared across API replicas."""
import os

from redis.exceptions import RedisError

from itlr.retrieval.cache import cache_namespace, configured_redis

_RESERVE = """
local rpm = tonumber(ARGV[1])
local tpm = tonumber(ARGV[2])
local tokens = tonumber(ARGV[3])
local calls = tonumber(redis.call('HGET', KEYS[1], 'calls') or '0')
local used = tonumber(redis.call('HGET', KEYS[1], 'tokens') or '0')
if (rpm > 0 and calls >= rpm) or (tpm > 0 and used + tokens > tpm) then
  return 0
end
redis.call('HINCRBY', KEYS[1], 'calls', 1)
redis.call('HINCRBY', KEYS[1], 'tokens', tokens)
if calls == 0 then redis.call('EXPIRE', KEYS[1], 60) end
return 1
"""


class ProviderBudgetError(RuntimeError):
    pass


def reserve_attempt(provider, messages, max_tokens):
    try:
        rpm = int(os.environ.get('ITLR_LLM_MAX_RPM', '0'))
        tpm = int(os.environ.get('ITLR_LLM_MAX_TPM', '0'))
    except ValueError:
        raise ProviderBudgetError('Invalid provider quota settings') from None
    if rpm < 0 or tpm < 0:
        raise ProviderBudgetError('Invalid provider quota settings')
    if not (rpm or tpm):
        return

    # Reserve bytes plus per-message framing and the maximum output. Actual provider
    # token use is tracked separately; this reservation is deliberately conservative.
    reserve = max_tokens + 32 + sum(len(msg['content'].encode('utf-8')) + 16 for msg in messages)
    key = f'itlr:provider:{cache_namespace()}:{provider}'
    client = configured_redis()
    try:
        accepted = client.eval(_RESERVE, 1, key, rpm, tpm, reserve) if client is not None else None
    except RedisError:
        accepted = None
    if accepted is None:
        raise ProviderBudgetError('Provider quota service unavailable')
    if not accepted:
        raise ProviderBudgetError('Provider quota exhausted')


_CIRCUIT_FAILURE = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if count >= tonumber(ARGV[1]) then return count end
count = redis.call('INCR', KEYS[1])
if count == 1 or count >= tonumber(ARGV[1]) then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
return count
"""


def _circuit_settings():
    try:
        threshold = int(os.environ.get('ITLR_LLM_CIRCUIT_THRESHOLD', '0'))
        seconds = int(os.environ.get('ITLR_LLM_CIRCUIT_SECONDS', '30'))
    except ValueError:
        raise ProviderBudgetError('Invalid provider circuit settings') from None
    if threshold < 0 or not 1 <= seconds <= 300:
        raise ProviderBudgetError('Invalid provider circuit settings')
    return threshold, seconds


def _circuit_key(provider):
    return f'itlr:provider-circuit:{cache_namespace()}:{provider}'


def check_circuit(provider):
    threshold, _ = _circuit_settings()
    if not threshold:
        return
    client = configured_redis()
    if client is None:
        raise ProviderBudgetError('Provider circuit service unavailable')
    try:
        failures = int(client.get(_circuit_key(provider)) or 0)
    except (RedisError, ValueError):
        raise ProviderBudgetError('Provider circuit service unavailable') from None
    if failures >= threshold:
        raise ProviderBudgetError('Provider circuit is open')


def circuit_failure(provider, exc):
    import logging

    threshold, seconds = _circuit_settings()
    if not threshold:
        return
    status = (getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
              or getattr(getattr(exc, 'response', None), 'status_code', None))
    transient = status in (408, 429) or isinstance(status, int) and status >= 500
    if status is None:
        from httpx import TransportError
        from openai import APIConnectionError

        transient = isinstance(exc, (OSError, TransportError, APIConnectionError))
    if not transient:
        return
    client = configured_redis()
    try:
        if client is not None:
            client.eval(_CIRCUIT_FAILURE, 1, _circuit_key(provider), threshold, seconds)
    except RedisError:
        logging.getLogger(__name__).warning('Provider circuit could not record failure')
