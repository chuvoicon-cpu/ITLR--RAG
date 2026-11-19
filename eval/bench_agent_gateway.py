"""End-to-end load via authenticated Web SSE and a real locally configured provider."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import sys
from time import perf_counter

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.bench_agent_http import percentiles
from scripts.check_agent_web import register

QUERIES = (
    'How do Docker Compose containers discover each other through a shared network?',
    'Khi dùng Docker Compose, các container tìm thấy nhau qua mạng chung như thế nào?',
    'Why does a Docker volume preserve data after a container is removed?',
    'When using Python logging, how are logger levels and handler levels evaluated?',
)


def sample(client, query):
    start = perf_counter()
    first_text = None
    final = None
    done = False
    error = None
    try:
        with client.stream('POST', '/api/chat/stream', timeout=180, json={'message': query},
                           headers={'X-CSRF-Token': client.cookies['csrf']}) as response:
            if response.status_code != 200:
                error = f'http_{response.status_code}'
            else:
                for line in response.iter_lines():
                    if not line.startswith('data: '):
                        continue
                    event = json.loads(line[6:])
                    if event['type'] == 'text' and first_text is None:
                        first_text = (perf_counter() - start) * 1000
                    elif event['type'] == 'final':
                        final = event
                    elif event['type'] == 'done':
                        done = True
                    elif event['type'] == 'error':
                        error = 'sse_error'
    except httpx.TimeoutException:
        error = 'timeout'
    except httpx.TransportError:
        error = 'transport_error'

    mode = final.get('generation_mode') if final else None
    citation = (final.get('citation_validation') or {}).get('status') if final else None
    error = error or ('missing_completion' if not done or not final else None)
    return {
        'elapsed_ms': (perf_counter() - start) * 1000, 'first_text_ms': first_text,
        'mode': mode, 'citation': citation, 'error': error,
        'web_timings': final.get('timings') if final else None,
        'accepted': error is None and mode == 'llm_extractive' and citation == 'valid',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    levels = []
    with ExitStack() as stack:
        clients = [stack.enter_context(register(args.web)) for _ in QUERIES]
        for concurrent in (1, 2, 4):
            start = perf_counter()
            with ThreadPoolExecutor(max_workers=concurrent) as workers:
                samples = list(workers.map(sample, clients[:concurrent], QUERIES[:concurrent]))
            duration = perf_counter() - start
            level = {
                'concurrency': concurrent, 'requests': len(samples),
                'rps': len(samples) / duration, 'accepted': sum(s['accepted'] for s in samples),
                'errors': sum(s['error'] is not None for s in samples),
                'elapsed_ms': percentiles([s['elapsed_ms'] for s in samples]),
                'ttft_ms': percentiles([s['first_text_ms'] for s in samples if s['first_text_ms'] is not None]),
                'samples': samples,
            }
            levels.append(level)
            args.out.write_text(json.dumps({'levels': levels, 'paid_cost_usd': None}, indent=2) + '\n')
            print(f'concurrency={concurrent} accepted={level["accepted"]}/{concurrent} errors={level["errors"]}', flush=True)
            if level['accepted'] != len(samples):
                break


if __name__ == '__main__':
    main()
