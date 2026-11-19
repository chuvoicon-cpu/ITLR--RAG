"""Evaluate the fixed native dense gate on existing blind retrieval judgments."""
import argparse
import hashlib
import json
from functools import partial
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.eval_qdrant_migration import run, summary
from eval.qdrant_native import build_native
from itlr.config import ROOT
from itlr.core.chunks import ChunkIndex
from itlr.core.embeddings import PRESETS, encode_query, load_model
from itlr.retrieval.qdrant_artifacts import load_public_corpus, verify_collection, version_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    path = ROOT / 'reports/production-blockers-evidence/frozen-blind-cases.jsonl'
    cases = [json.loads(line) for line in path.read_text().splitlines()]
    tuning_queries = {json.loads(line)['query'].strip().casefold()
                      for f in ('engineering_queries', 'engineering_confirmation_queries', 'release_queries')
                      for line in (ROOT / f'eval/{f}.jsonl').read_text().splitlines()}
    assert not any(c['query'].strip().casefold() in tuning_queries for c in cases)
    version, rows, vectors, payloads = load_public_corpus(args.artifacts)
    store = version_store(version, len(rows), vectors.shape[1])
    verify_collection(store, vectors, payloads)
    native = build_native(version_store(version, len(rows), vectors.shape[1], writer=True), rows, vectors, payloads)
    preset = PRESETS['e5-base']
    model = load_model(preset['model_name'])
    for case in cases:
        case['vector'] = encode_query(model, case['query'], preset)
        case['judgments'] = [{**j, 'item_id': int(j['item_id'])} for j in case['judgments']]
    report = {'fixture_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'manifest': version, 'min_relevance': .84, 'human_reviewed': None,
              'exact_overlap_with_tuning': 0, 'cases': {c['id']: {
                  'kind': c['kind'], 'language': c['language'],
                  'expected': [j['item_id'] for j in c['judgments']]} for c in cases}}
    for name, retrieve in [('phase_a', ChunkIndex(rows, dense_store=store).search),
                           ('native', partial(native.search, dense_gate=True))]:
        hits, timing = run(retrieve, cases, 1)
        report[name] = {**summary(cases, hits), 'latency': timing}
        for case, hits_for_case in zip(cases, hits, strict=True):
            report['cases'][case['id']][name] = [row['chunk_id'] for row in hits_for_case]
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(report['phase_a'], report['native'])


if __name__ == '__main__':
    main()
