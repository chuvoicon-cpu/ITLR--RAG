"""Compare Qdrant phase A with the FAISS reference on frozen release qrels."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.eval_release_retrieval import metrics, peak_process_rss_mib
from itlr import config
from itlr.core.chunks import ChunkIndex
from itlr.core.embeddings import PRESETS, encode_query, load_model
from itlr.retrieval.qdrant_artifacts import load_public_corpus, verify_collection, version_store
from itlr.retrieval.service import DEFAULT_SEARCH_MIN_PCT


def run(search_index, prepared, concurrency):
    def search(case):
        query, vector = case['query'], case['vector']
        start = perf_counter()
        hits = search_index(query, vector, top_k=5, min_relevance=DEFAULT_SEARCH_MIN_PCT / 100,
                            unique_items=True)
        elapsed = (perf_counter() - start) * 1000
        return hits, elapsed

    start = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        outputs = list(pool.map(search, prepared))
    wall = perf_counter() - start
    return [hits for hits, _ in outputs], {
        'p50_ms': float(np.percentile([ms for _, ms in outputs], 50)),
        'p95_ms': float(np.percentile([ms for _, ms in outputs], 95)),
        'p99_ms': float(np.percentile([ms for _, ms in outputs], 99)),
        'rps': len(outputs) / wall,
        'peak_active_limit': concurrency,
        'errors': 0,
    }


def summary(cases, hits):
    positive = []
    negative = []
    for case, results in zip(cases, hits, strict=True):
        expected = {j['item_id'] for j in case['judgments']}
        ids = [int(r['item_id']) for r in results]
        if expected:
            positive.append(metrics(ids, expected, 5))
        else:
            negative.append(not ids)
    return {
        **{key + '@5': float(np.mean([m[key] for m in positive])) for key in ('recall', 'mrr', 'ndcg')},
        'negative_empty_count': sum(negative),
        'negative_count': len(negative),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--native', action='store_true', help='Evaluate phase B only after parity; writes an experimental collection')
    args = parser.parse_args()
    case_paths = [config.ROOT / 'eval' / name for name in (
        'release_queries.jsonl', 'engineering_confirmation_queries.jsonl')]
    cases = [json.loads(line) for path in case_paths for line in path.read_text(encoding='utf-8').splitlines()]
    version, rows, matrix, payloads = load_public_corpus(args.artifacts)
    remote = version_store(version, len(rows), matrix.shape[1])
    verify_collection(remote, matrix, payloads)
    preset = PRESETS['e5-base']
    model = load_model(preset['model_name'])
    prepared = [{**case, 'vector': encode_query(model, case['query'], preset)} for case in cases]

    # FAISS constructor should receive original embeddings, as the normal API does.
    import pickle
    with (args.artifacts / 'chunk_embeddings.pkl').open('rb') as stream:
        faiss = ChunkIndex(rows, pickle.load(stream))
    qdrant = ChunkIndex(rows, dense_store=remote)
    baseline, baseline_perf = run(faiss.search, prepared, 1)
    candidate, candidate_perf = run(qdrant.search, prepared, 1)
    by_case = []
    for case, left, right in zip(cases, baseline, candidate, strict=True):
        by_case.append({
            'id': case['id'], 'kind': case['kind'],
            'faiss': [hit['chunk_id'] for hit in left], 'qdrant': [hit['chunk_id'] for hit in right],
        })
    drift = [row['id'] for row in by_case if row['faiss'] != row['qdrant']]
    load = {'1': candidate_perf}
    if not drift:
        for concurrency in (2, 4, 8):
            hits, load[str(concurrency)] = run(qdrant.search, prepared, concurrency)
            if hits != candidate:
                raise RuntimeError('Concurrent Qdrant rankings changed')
    report = {
        'scope': 'same precomputed E5 query vectors, CPU, loopback Qdrant, ChunkIndex, no reranker/LLM',
        'labels': 'frozen engineer-authored qrels', 'min_pct': DEFAULT_SEARCH_MIN_PCT,
        'manifest_sha256': version, 'items': len({row['item_id'] for row in rows}), 'points': len(rows),
        'queries': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in case_paths},
        'faiss': {**summary(cases, baseline), 'serial': baseline_perf},
        'qdrant': {**summary(cases, candidate), 'load': load},
        'rank_drift': drift, 'cases': by_case, 'peak_process_rss_mib': peak_process_rss_mib(),
        'ttft_ms': None, 'provider_cost': None, 'human_faithfulness': None,
    }
    if args.native and not drift:
        from eval.qdrant_native import build_native

        writer = version_store(version, len(rows), matrix.shape[1], writer=True)
        hybrid = build_native(writer, rows, matrix, payloads)
        native_hits, native_perf = run(hybrid.search, prepared, 1)
        report['native_experiment'] = {
            **summary(cases, native_hits), 'serial': native_perf,
            'independent_dense_sparse': True,
            'changed_rankings': sum(
                [h['chunk_id'] for h in a] != [h['chunk_id'] for h in b]
                for a, b in zip(candidate, native_hits, strict=True)),
            'cases': [{'id': case['id'], 'chunks': [hit['chunk_id'] for hit in hits]}
                      for case, hits in zip(cases, native_hits, strict=True)],
        }

        gated, gated_perf = run(partial(hybrid.search, dense_gate=True), prepared, 1)
        report['native_dense_gated'] = {
            **summary(cases, gated), 'serial': gated_perf,
            'cases': [{'id': case['id'], 'chunks': [hit['chunk_id'] for hit in hits]}
                      for case, hits in zip(cases, gated, strict=True)],
            'human_reviewed_cases': None, 'promotion_allowed': False,
        }
        diagnostics = []
        for case, ungated, hard_gate_hits in zip(prepared, native_hits, gated, strict=True):
            if case['judgments']:
                continue
            vector = case['vector']
            threshold = DEFAULT_SEARCH_MIN_PCT / 100
            branches = hybrid.branches(case['query'], vector, min_relevance=threshold, candidate_k=32)
            by_branch = {}
            for branch in branches:
                hits = hybrid.store.request('POST', f'{hybrid.store.path}/points/query', branch)['points']
                by_branch[branch['using']] = {hit['id']: (rank, hit['score'])
                                              for rank, hit in enumerate(hits, start=1)}
            full_dense = remote.dense_search(vector.reshape(1, -1), min_relevance=-1)
            lookup = {payload['chunk_id']: i for i, payload in enumerate(payloads)}
            traces = []
            fused = hybrid.store.request('POST', f'{hybrid.store.path}/points/query', {
                'prefetch': branches, 'query': {'rrf': {'k': 61}}, 'limit': 32, 'with_payload': False,
            })['points']
            fused_scores = {hit['id']: hit['score'] for hit in fused}
            for hit in ungated:
                idx = lookup[hit['chunk_id']]
                traces.append({
                    'chunk_id': hit['chunk_id'], 'source_id': payloads[idx]['source_id'],
                    'excerpt': hit['chunk_text'][:240], 'payload_version': payloads[idx]['version'],
                    'approval_state': payloads[idx]['approval_state'],
                    'dense': full_dense[idx], 'rrf': fused_scores[idx],
                    'sparse_rank_score': by_branch.get('bm25', {}).get(idx),
                    'dense_rank_score': by_branch.get('dense', {}).get(idx),
                })
            diagnostics.append({
                'id': case['id'], 'query': case['query'], 'judgments': case['judgments'],
                'max_dense': max(full_dense.values()), 'threshold': threshold, 'top_k': 5,
                'branch_filters': {b['using']: b['filter'] for b in branches},
                'top_hits': traces, 'gated_chunks': [h['chunk_id'] for h in hard_gate_hits],
            })
        report['negative_diagnostics'] = diagnostics
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(f'{len(cases)} queries, {len(drift)} changed chunk rankings')
    return int(bool(drift))


if __name__ == '__main__':
    raise SystemExit(main())
