"""Rate limiting TRONG TIẾN TRÌNH (sliding window) cho API FastAPI.

Giới hạn theo client IP trên các endpoint đắt (chat gọi LLM, search chạy retrieval).
Chỉ dùng một worker và một replica. Mặc định bỏ qua forwarding headers; sau reverse
proxy chỉ bật proxy headers với danh sách IP proxy tin cậy tường minh. Cấu hình qua env (đọc LẠI mỗi lần gọi — đổi runtime không cần restart):

    ITLR_RATE_SEARCH_PER_MIN = 120   (0 = tắt limiter cho bucket này)
    ITLR_RATE_CHAT_PER_MIN   = 30

429 trả kèm Retry-After để client/backoff đúng nghĩa, không âm thầm bỏ qua.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import logging
import os
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache
from uuid import uuid4

from fastapi import HTTPException, Request
from redis.exceptions import RedisError

from itlr.retrieval.cache import cache_namespace, configured_redis

logger = logging.getLogger(__name__)
_REDIS_LIMIT = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if count >= tonumber(ARGV[1]) then return redis.call('TTL', KEYS[1]) + 1 end
if redis.call('INCR', KEYS[1]) == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return 0
"""


def _distributed_enabled():
    return os.environ.get('ITLR_REDIS_RATE_LIMIT') == '1'


def _distributed_enforce(bucket, key, limit):
    client = configured_redis()
    scope = hashlib.sha256(f'{cache_namespace()}:{bucket}:{key}'.encode()).hexdigest()
    try:
        wait = client.eval(_REDIS_LIMIT, 1, 'itlr:limit:' + scope, limit) if client is not None else None
    except RedisError:
        wait = None
    if wait is None:
        logger.warning('Distributed rate limit service unavailable')
        raise HTTPException(status_code=503, detail='Rate limiter unavailable')
    if wait:
        raise HTTPException(status_code=429, detail=f'Quá nhiều yêu cầu ({bucket}).',
                            headers={'Retry-After': str(wait)})


_LOCK = threading.Lock()
# Bucket này -> (IP -> deque timestamps). Giữ trong RAM; chỉ nhãn IP nên nhẹ.
_HITS: dict[str, dict[str, deque[float]]] = defaultdict(dict)
MAX_TRACKED_KEYS = 100_000  # chống phình RAM khi bị dội request giả IP


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 0:
        return default
    return value


def client_ip(request: Request) -> str:
    host = request.client.host if request.client else ""
    return host or "unknown"


def enforce(request: Request, bucket: str, default_per_min: int) -> None:
    limit = _env_int(f"ITLR_RATE_{bucket}_PER_MIN", default_per_min)
    if limit <= 0:
        return
    key = client_ip(request)
    if _distributed_enabled():
        return _distributed_enforce(bucket, key, limit)
    now = time.monotonic()
    with _LOCK:
        per_ip = _HITS[bucket]
        if key not in per_ip and len(per_ip) >= MAX_TRACKED_KEYS:
            expired = [ip for ip, times in per_ip.items() if not times or now - times[-1] > 60]
            for ip in expired:
                del per_ip[ip]
            if len(per_ip) >= MAX_TRACKED_KEYS:
                raise HTTPException(status_code=429, detail="Rate limiter capacity reached",
                                    headers={"Retry-After": "60"})
        hits = per_ip.setdefault(key, deque())
        while hits and now - hits[0] > 60.0:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Quá nhiều yêu cầu ({bucket}). Thử lại sau ít phút.",
                headers={"Retry-After": "60"},
            )
        hits.append(now)


def enforce_chat(request: Request, default_per_min: int) -> None:
    key = os.environ.get('ITLR_CHAT_PRINCIPAL_KEY', '')
    token = request.headers.get('X-ITLR-Principal')
    match = re.fullmatch(r'v1[.]([1-9][0-9]{0,9})[.]([0-9]{10})[.]([0-9a-f]{64})', token or '')
    if key and match:
        user_id, issued, signature = match.groups()
        signed = f'v1.{user_id}.{issued}.{request.url.path}'.encode()
        valid = hmac.compare_digest(signature, hmac.new(key.encode(), signed, hashlib.sha256).hexdigest())
        if valid and -5 <= time.time() - int(issued) <= 60:
            limit = _env_int('ITLR_CHAT_USER_PER_MIN', 12)
            if limit:
                _distributed_enforce('CHAT_USER', user_id, limit)
            return
    if os.environ.get('ITLR_REQUIRE_WEB_CHAT') == '1':
        raise HTTPException(status_code=401, detail='Authenticated Web chat required')
    enforce(request, 'CHAT', default_per_min)


_CLUSTER_CLAIM = """
local now = tonumber(redis.call('TIME')[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then return 0 end
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[2]), ARGV[3])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]) + 1)
return 1
"""
CLUSTER_LEASE_SECONDS = 900


def _acquire_cluster_slot(limit):
    key = 'itlr:chat:active:' + hashlib.sha256(cache_namespace().encode()).hexdigest()
    member = uuid4().hex
    client = configured_redis()
    try:
        accepted = client.eval(_CLUSTER_CLAIM, 1, key, limit, CLUSTER_LEASE_SECONDS, member) if client else None
    except RedisError:
        accepted = None
    if accepted is None:
        raise HTTPException(status_code=503, detail='Chat capacity service unavailable')
    if not accepted:
        raise HTTPException(status_code=429, detail='Cluster chat capacity reached', headers={'Retry-After': '1'})

    def release():
        try:
            client.zrem(key, member)
        except RedisError:
            logger.warning('Chat slot release deferred to lease expiry')
    return release



@lru_cache(maxsize=1)
def _chat_slots(limit):
    return threading.BoundedSemaphore(limit)


def acquire_chat_slot():
    """Per-process backpressure, independent of the distributed request quota."""
    limit = _env_int('ITLR_CHAT_CONCURRENCY', 0)
    cluster_limit = _env_int('ITLR_CHAT_CLUSTER_CONCURRENCY', 0)
    permits = _chat_slots(limit) if limit else None
    if permits is not None and not permits.acquire(blocking=False):
        raise HTTPException(status_code=429, detail='Chat capacity reached', headers={'Retry-After': '1'})
    try:
        release_cluster = _acquire_cluster_slot(cluster_limit) if cluster_limit else None
    except BaseException:
        if permits is not None:
            permits.release()
        raise

    def release():
        try:
            if release_cluster is not None:
                release_cluster()
        finally:
            if permits is not None:
                permits.release()
    return release


def reset(state: dict | None = None) -> None:
    """Chỉ dành cho test: dọn sạch đếm rate."""
    with _LOCK:
        _HITS.clear()


def validate_workers() -> None:
    """In-memory buckets require exactly one process; deployment must enforce one replica."""
    principal_key = os.environ.get('ITLR_CHAT_PRINCIPAL_KEY', '')
    required = os.environ.get('ITLR_REQUIRE_WEB_CHAT') == '1'
    if (principal_key or required) and len(principal_key.encode()) < 32:
        raise RuntimeError('ITLR_CHAT_PRINCIPAL_KEY must be at least 32 bytes')
    if principal_key or _env_int('ITLR_CHAT_CLUSTER_CONCURRENCY', 0):
        if configured_redis() is None:
            raise RuntimeError('ITLR_REDIS_URL is required for Web or cluster chat quota')
    if _distributed_enabled():
        if configured_redis() is None:
            raise RuntimeError('ITLR_REDIS_URL is required for distributed rate limiting')
        return
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        if os.environ.get(name, "1") != "1":
            raise RuntimeError(f"{name} must be 1 with the in-process rate limiter")
