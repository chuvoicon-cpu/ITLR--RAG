"""Live service lifecycle checks against explicitly disposable Qdrant/Redis endpoints."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
import hashlib
from time import sleep
from uuid import uuid4

import httpx
import numpy as np
from redis.exceptions import RedisError

from itlr.api.ratelimit import _REDIS_LIMIT
from itlr.retrieval.cache import PublicCache, redis_client
from itlr.retrieval.qdrant_artifacts import promote, stage_collection, verify_collection
from itlr.retrieval.vector_store import QdrantUnavailable, QdrantVectorStore


def qdrant_checks(url):
    run = 'itlr_check_' + uuid4().hex
    alias = run + '_active'
    old = QdrantVectorStore(url, run + '_a', 'a', 2, 2)
    new = QdrantVectorStore(url, run + '_b', 'b', 2, 2)
    restored = QdrantVectorStore(url, run + '_restored', 'b', 2, 2)
    matrix = np.eye(2, dtype=np.float32)
    vector = np.array([[1.0, 0.0]], dtype=np.float32)

    def payload(version):
        return [{'version': version, 'approval_state': 'approved',
                 'chunk_id': f'{i + 10}:0', 'item_id': i + 10} for i in range(2)]

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(stage_collection, store, matrix, payload(store.version)) for store in (old, new)]
            for future in futures:
                future.result()
        stage_collection(old, matrix, payload('a'))
        assert old.exact_chunk('10:0') == payload('a')[0]
        assert old.dense_search(vector, metadata={'item_id': 11}, min_relevance=-1) == {1: 0.}
        assert promote(old, alias) is None
        assert promote(new, alias) == old.collection
        assert old.dense_search(vector, min_relevance=.84) == {0: 1.}
        name = new.request('POST', f'{new.path}/snapshots?wait=true')['name']
        assert name
        with httpx.Client(base_url=url, timeout=15, trust_env=False) as http:
            snapshot = http.get(f'{new.path}/snapshots/{name}').raise_for_status().content
            with_checksum = {'wait': 'true', 'priority': 'snapshot',
                             'checksum': hashlib.sha256(snapshot).hexdigest()}
            recovered = http.post(f'{restored.path}/snapshots/upload', params=with_checksum,
                                  files={'snapshot': (name, snapshot)})
            assert recovered.raise_for_status().json()['result'] is True
        verify_collection(restored, matrix, payload('b'))
        assert promote(old, alias) == new.collection
        assert {'alias_name': alias, 'collection_name': old.collection} in old.request('GET', '/aliases')['aliases']
        wrong = QdrantVectorStore(url, old.collection, 'wrong', 2, 2)
        try:
            wrong.health()
        except QdrantUnavailable:
            pass
        else:
            raise AssertionError('Wrong version accepted')
        new.upsert_chunks([{
            'id': 0, 'vector': {'dense': [0., 1.]}, 'payload': payload('b')[0],
        }])
        assert new.dense_search(vector, min_relevance=.84) == {}
        new.delete_document(10)
        assert new.exact_chunk('10:0') is None
        verify_collection(old, matrix, payload('a'))
    finally:
        for store in (old, new, restored):
            with suppress(QdrantUnavailable):
                store.request('DELETE', store.path)
    print('Qdrant: parallel stage, replay, exact ID, filter, revision guard, alias rollback, snapshot restore, update/delete PASS')


def redis_checks(url):
    redis = redis_client(url)
    prefix = 'itlr_check_' + uuid4().hex
    cache = PublicCache(redis, prefix, 'one', 'E5')
    calls = []

    def fetch():
        calls.append(1)
        sleep(.08)
        return [123]

    key = prefix + ':limit'
    try:
        with ThreadPoolExecutor(max_workers=8) as workers:
            assert list(workers.map(lambda _: cache.read('response', ['HTML'], fetch), range(8))) == [[123]] * 8
            assert len(calls) == 1
            results = list(workers.map(lambda _: redis.eval(_REDIS_LIMIT, 1, key, 3), range(8)))
            assert results.count(0) == 3
        cache2 = PublicCache(redis, prefix, 'two', 'E5')
        assert cache2.read('response', ['HTML'], lambda: [456]) == [456]
        assert cache.read('response', ['HTML'], lambda: []) == [123]
    finally:
        with suppress(RedisError):
            redis.delete(key, cache.key('response', ['HTML']),
                         PublicCache(redis, prefix, 'two', 'E5').key('response', ['HTML']))
    print('Redis: concurrent cache fill, revision isolation, atomic rate quota PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qdrant', required=True)
    parser.add_argument('--redis', required=True)
    args = parser.parse_args()
    qdrant_checks(args.qdrant)
    redis_checks(args.redis)
