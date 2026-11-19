"""Single-host HTTP search and no-provider chat benchmark on an isolated deployment."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
from threading import Lock
from time import perf_counter

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.eval_generation import is_refusal
from itlr import config


def percentiles(values):
    return {f'p{p}': float(np.percentile(values, p)) for p in (50, 95, 99)} if values else None


def search_load(client, cases):
    levels = []
    for concurrency in (1, 2, 4, 8):
        lock, active, peak = Lock(), 0, 0

        def search(case):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            start = perf_counter()
            try:
                response = client.post('/api/search', json={'query': case['query'], 'min_pct': 84})
                status = response.status_code
            except httpx.TimeoutException:
                status = 'timeout'
            except httpx.HTTPError:
                status = 'transport_error'
            finally:
                with lock:
                    active -= 1
            return status, (perf_counter() - start) * 1000

        start = perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            samples = list(pool.map(search, cases))
        elapsed = perf_counter() - start
        errors = sum(status != 200 for status, _ in samples)
        levels.append({
            'concurrency': concurrency, 'peak_active_requests': peak, 'requests': len(samples),
            'rps': len(samples) / elapsed, 'status_counts': {
                str(code): sum(status == code for status, _ in samples) for code in {s for s, _ in samples}
            },
            'error_rate': errors / len(samples),
            'timeout_rate': sum(status == 'timeout' for status, _ in samples) / len(samples),
            'latency_ms': percentiles([ms for _, ms in samples]),
        })
        if errors:
            break
    return levels


def template_eval(client, cases):
    result = []
    for case in cases:
        start = perf_counter()
        with client.stream('POST', '/api/chat/stream', json={'message': case['query']}) as response:
            response.raise_for_status()
            final, ttft, done = None, None, False
            for line in response.iter_lines():
                if not line.startswith('data: '):
                    continue
                event = json.loads(line[6:])
                if event['type'] == 'text' and ttft is None:
                    ttft = (perf_counter() - start) * 1000
                if event['type'] == 'final':
                    final = event
                if event['type'] == 'done':
                    done = True
            duration = (perf_counter() - start) * 1000
        assert done and final and final['generation_mode'] in {'template', 'extractive', 'insufficient_evidence'}
        expected = {int(j['item_id']) for j in case['judgments']}
        retrieved = {s['item_id'] for s in final['sources'] if 'item_id' in s}
        result.append({
            'id': case['id'], 'kind': case['kind'], 'language': case['language'],
            'mode': final['generation_mode'], 'citation_status': final.get('citation_validation', {}).get('status'),
            'refused': final['generation_mode'] == 'insufficient_evidence' or is_refusal(final['response']),
            'judged_source_found': bool(expected & retrieved) if expected else None,
            'ttft_ms': ttft, 'duration_ms': duration,
        })
    return {
        'cases': result, 'ttft_ms': percentiles([r['ttft_ms'] for r in result if r['ttft_ms'] is not None]),
        'duration_ms': percentiles([r['duration_ms'] for r in result]),
        'human_faithfulness': None, 'provider_cache_hit_rate': None, 'provider_cost_usd': None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    search_path = config.ROOT / 'eval/release_queries.jsonl'
    generation_path = config.ROOT / 'reports/production-blockers-evidence/frozen-blind-cases.jsonl'

    def cases(path):
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

    with httpx.Client(base_url=args.api, timeout=15, trust_env=False) as client:
        health = client.get('/health').raise_for_status().json()
        repeated = []
        for _ in range(15):
            start = perf_counter()
            client.post('/api/search', json={'query': 'Docker'}).raise_for_status()
            repeated.append((perf_counter() - start) * 1000)
        data = {
            'health': health, 'search_suite_sha256': hashlib.sha256(search_path.read_bytes()).hexdigest(),
            'generation_suite_sha256': hashlib.sha256(generation_path.read_bytes()).hexdigest(),
            'search': search_load(client, cases(search_path)),
            'repeated_public_docker_latency_ms': percentiles(repeated),
            'chat_template_or_extractive': template_eval(client, cases(generation_path)),
        }
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    return int(any(level['error_rate'] for level in data['search']))


if __name__ == '__main__':
    raise SystemExit(main())
