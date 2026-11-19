"""Bounded single-host test for two isolated API replicas and one disposable Web."""
import argparse
import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep, time

import httpx

from itlr.agent_jobs import connect
from itlr.retrieval.cache import configured_redis, cache_namespace
from scripts.check_agent_web import register


def signature(path, uid):
    key = os.environ['ITLR_CHAT_PRINCIPAL_KEY'].encode()
    value = f'v1.{uid}.{int(time())}'
    mac = hmac.new(key, f'{value}.{path}'.encode(), hashlib.sha256).hexdigest()
    return {'X-ITLR-Principal': f'{value}.{mac}'}


def check_web(web):
    with register(web) as owner, register(web) as peer:
        def post(client, message, conversation=None):
            body = {'message': message}
            if conversation:
                body['conversation_id'] = conversation
            return client.post('/api/chat', json=body, headers={'X-CSRF-Token': client.cookies['csrf']})

        greeting = 'Xin chào'
        conversation = post(owner, greeting).raise_for_status().json()['conversation_id']
        assert post(peer, greeting, conversation).status_code == 404
        assert not any(row['id'] == conversation for row in peer.get('/api/conversations').raise_for_status().json())
        assert peer.get('/api/agent/handoffs').status_code == 403
        assert peer.get('/api/agent/handoffs', headers={'X-Tenant-ID': 'another'}).status_code == 400
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: post(owner, greeting, conversation).status_code, range(2)))
        assert results == [200, 200]
        with connect() as db:
            assert db.execute('SELECT count(*) AS n FROM messages WHERE conversation_id=%s',
                              (conversation,)).fetchone()['n'] == 6
    print('Web: real PostgreSQL conversation IDOR, privilege/tenant denial, and concurrent atomic writes PASS', flush=True)


def check_replicas(clients):
    assert clients[0].get('/health').raise_for_status().json() == clients[1].get('/health').raise_for_status().json()
    for index in range(12):
        path = '/api/chat'
        r = clients[index % 2].post(path, json={'message': 'Xin chào'}, headers=signature(path, 923456))
        assert r.status_code == 200, r.status_code
    assert clients[1].post('/api/chat', json={'message': 'Xin chào'},
                           headers=signature('/api/chat', 923456)).status_code == 429
    assert clients[1].post('/api/chat', json={'message': 'Xin chào'},
                           headers=signature('/api/chat', 923457)).status_code == 200

    from itlr.retrieval.cache import PublicCache
    redis = configured_redis()
    artifact = clients[0].get('/health').json()['artifacts']['collection']
    cache = PublicCache(redis, cache_namespace(), artifact, 'intfloat/multilingual-e5-base')
    args = ['Docker', None, 84, 'search']
    old_key = cache.key('response', args)
    redis.delete(old_key)
    search = {'query': 'Docker', 'min_pct': 84}
    first = clients[0].post('/api/search', json=search).raise_for_status().json()
    assert redis.exists(old_key)
    assert first == clients[1].post('/api/search', json=search).raise_for_status().json()
    assert 'itlr_cache_events_total{layer="response",outcome="hit"}' in clients[1].get('/metrics/prometheus').text

    key = 'itlr:chat:active:' + hashlib.sha256(cache_namespace().encode()).hexdigest()
    path = '/api/chat/stream'
    question = 'How do Docker Compose containers find each other across networks?'
    with clients[0].stream('POST', path, json={'message': question}, headers=signature(path, 923458)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith('data: ') and json.loads(line[6:])['type'] == 'sources':
                break
        else:
            raise AssertionError('Stream did not begin')
        assert redis.zcard(key) == 1
        sleep(.5)
    deadline = monotonic() + 5
    while redis.zcard(key) and monotonic() < deadline:
        sleep(.05)
    assert redis.zcard(key) == 0
    print('Two replicas: shared quota, shared cache, and SSE disconnect releases distributed permit PASS', flush=True)


def soak(clients, seconds, out):
    from eval.bench_agent_http import percentiles

    start = monotonic()
    stats = [[], []]
    n = 0
    while monotonic() - start < seconds:
        index = n % 2
        begin = monotonic()
        result = clients[index].post('/api/search', json={'query': 'Docker', 'min_pct': 84})
        stats[index].append({'status': result.status_code, 'ms': (monotonic() - begin) * 1000})
        n += 1
        sleep(max(0, start + n - monotonic()))
    report = {'duration_seconds': monotonic() - start, 'target_aggregate_rps': 1,
              'workload': 'exact cache lookup Docker, alternating replicas',
              'replicas': [{'requests': len(group), 'non_200': sum(r['status'] != 200 for r in group),
                            'latency_ms': percentiles([r['ms'] for r in group])} for group in stats]}
    out.write_text(json.dumps(report, indent=2) + '\n')
    assert all(r['non_200'] == 0 for r in report['replicas'])
    print('Soak PASS', report, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', required=True, nargs=2)
    parser.add_argument('--web', required=True)
    parser.add_argument('--seconds', type=int, default=120, choices=range(20, 301))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check_web(args.web)
    with httpx.Client(base_url=args.api[0], timeout=20, trust_env=False) as a, \
            httpx.Client(base_url=args.api[1], timeout=20, trust_env=False) as b:
        check_replicas((a, b))
        soak((a, b), args.seconds, args.out)


if __name__ == '__main__':
    main()
