"""Bounded Redis caching for deterministic reads of the public corpus."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from time import monotonic, sleep
from uuid import uuid4

from prometheus_client import Counter
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

CACHE_EVENTS = Counter('itlr_cache_events', 'Public cache outcomes', ['layer', 'outcome'])
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  if ARGV[2] ~= '' then redis.call('SET', KEYS[2], ARGV[2], 'EX', 300) end
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@lru_cache(maxsize=2)
def redis_client(url):
    return Redis.from_url(url, socket_timeout=.2, socket_connect_timeout=.2,
                          retry=Retry(NoBackoff(), 0), max_connections=32)


def configured_redis():
    url = os.environ.get('ITLR_REDIS_URL')
    return redis_client(url) if url else None


def cache_namespace():
    return os.environ.get('ITLR_CACHE_NAMESPACE', 'itlr-local')


@lru_cache(maxsize=1)
def _public_queries():
    from itlr.chatbot.knowledge_base import CONCEPTS
    return frozenset(
        str(alias).strip()
        for concept in CONCEPTS.values() for alias in [concept['name'], *concept.get('aliases', [])]
    )


def public_query(query):
    return query in _public_queries()


class CacheBusy(RuntimeError):
    """A healthy shared cache has an in-flight fill beyond the wait budget."""


class PublicCache:
    """Each computation must be a side-effect free public read."""

    def __init__(self, client, namespace, revision, model):
        self.client = client
        self.scope = [namespace, 'public-catalog', 'policy-v1', revision, model]

    def key(self, layer, args):
        epoch = os.environ.get('ITLR_CACHE_EPOCH', '1')
        packed = json.dumps([self.scope, epoch, layer, args], separators=(',', ':'), ensure_ascii=False)
        return 'itlr:cache:' + hashlib.sha256(packed.encode()).hexdigest()

    def read(self, layer, args, load):
        key = self.key(layer, args)
        lease = key + ':lease'
        owner = uuid4().hex
        try:
            cached = self.client.get(key)
            if cached is not None:
                CACHE_EVENTS.labels(layer, 'hit').inc()
                return json.loads(cached)
            acquired = self.client.set(lease, owner, nx=True, ex=10)
            if not acquired:
                deadline = monotonic() + 2
                while monotonic() < deadline:
                    sleep(.05)
                    cached = self.client.get(key)
                    if cached is not None:
                        CACHE_EVENTS.labels(layer, 'coalesced').inc()
                        return json.loads(cached)
                    acquired = self.client.set(lease, owner, nx=True, ex=10)
                    if acquired:
                        break
        except (RedisError, ValueError):
            CACHE_EVENTS.labels(layer, 'unavailable').inc()
            return load()

        if not acquired:
            CACHE_EVENTS.labels(layer, 'wait_expired').inc()
            raise CacheBusy('Public cache fill is busy')
        payload = ''
        try:
            # A previous lease holder may have published between GET and SET NX.
            try:
                cached = self.client.get(key)
                if cached is not None:
                    CACHE_EVENTS.labels(layer, 'coalesced').inc()
                    return json.loads(cached)
            except (RedisError, ValueError):
                CACHE_EVENTS.labels(layer, 'unavailable').inc()
            CACHE_EVENTS.labels(layer, 'miss').inc()
            value = load()
            try:
                payload = json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(',', ':'))
            except (ValueError, TypeError):
                CACHE_EVENTS.labels(layer, 'uncacheable').inc()
            return value
        finally:
            try:
                self.client.eval(_RELEASE, 2, lease, key, owner, payload)
            except RedisError:
                CACHE_EVENTS.labels(layer, 'unavailable').inc()


def configured_public_cache(revision, model):
    client = configured_redis()
    return PublicCache(client, cache_namespace(), revision, model) if client is not None else None
