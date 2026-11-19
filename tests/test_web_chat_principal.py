import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from itlr.api import ratelimit


SECRET = 'fixture-only-chat-key-at-least-32-characters'


def signed(path='/api/chat', uid=11, age=0):
    timestamp = int(time.time()) - age
    value = f'v1.{uid}.{timestamp}'
    mac = hmac.new(SECRET.encode(), f'{value}.{path}'.encode(), hashlib.sha256).hexdigest()
    return f'{value}.{mac}'


def request(path, value=None):
    headers = [] if value is None else [(b'x-itlr-principal', value.encode())]
    return Request({'type': 'http', 'path': path, 'method': 'POST',
                    'headers': headers, 'client': ('127.0.0.1', 42)})


def test_chat_quota_uses_verified_user_and_binds_path_and_expiry(monkeypatch):
    monkeypatch.setenv('ITLR_CHAT_PRINCIPAL_KEY', SECRET)
    monkeypatch.setenv('ITLR_REQUIRE_WEB_CHAT', '1')
    monkeypatch.setenv('ITLR_REDIS_RATE_LIMIT', '1')
    limits = []
    monkeypatch.setattr(ratelimit, '_distributed_enforce', lambda *args: limits.append(args))
    ratelimit.enforce_chat(request('/api/chat', signed(uid=11)), 30)
    ratelimit.enforce_chat(request('/api/chat', signed(uid=19)), 30)
    assert limits == [('CHAT_USER', '11', 12), ('CHAT_USER', '19', 12)]
    for req in (request('/api/chat'), request('/api/chat/stream', signed()),
                request('/api/chat', signed(age=200)), request('/api/chat', '11')):
        with pytest.raises(HTTPException) as exc:
            ratelimit.enforce_chat(req, 30)
        assert exc.value.status_code == 401


def test_distributed_slot_denial_is_fail_closed(monkeypatch):
    class Redis:
        def eval(self, *_):
            return 0

    monkeypatch.setenv('ITLR_CHAT_CLUSTER_CONCURRENCY', '2')
    monkeypatch.setattr(ratelimit, 'configured_redis', Redis)
    with pytest.raises(HTTPException) as exc:
        ratelimit.acquire_chat_slot()
    assert exc.value.status_code == 429
