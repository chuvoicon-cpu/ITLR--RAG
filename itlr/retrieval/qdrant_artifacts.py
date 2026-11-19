"""Versioned public corpus import and promotion. Invoked by operators, outside requests."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pickle
import re

import numpy as np

from itlr import config
from itlr.core.embeddings import PRESETS
from itlr.retrieval.vector_store import FAISSVectorStore, QdrantUnavailable, QdrantVectorStore, qdrant_name
from itlr.versioning import MANIFEST, VersionError, probe_ok, verify_integrity


def version_store(version, count, dimension, *, writer=False):
    if not version or not re.fullmatch(r'[0-9a-f]{64}', version):
        raise VersionError('Qdrant requires an artifact manifest fingerprint')
    namespace = os.environ.get('ITLR_QDRANT_NAMESPACE', 'itlr_chunks')
    url = os.environ.get('ITLR_QDRANT_URL')
    if not url:
        raise VersionError('ITLR_QDRANT_URL is required for Qdrant')
    key = os.environ.get('ITLR_QDRANT_WRITE_KEY' if writer else 'ITLR_QDRANT_API_KEY')
    try:
        return QdrantVectorStore(url, f'{namespace}_{version}', version, dimension, count, api_key=key)
    except ValueError:
        raise VersionError('Invalid Qdrant configuration') from None


def active_alias():
    alias = os.environ.get('ITLR_QDRANT_ALIAS') or os.environ.get('ITLR_QDRANT_NAMESPACE', 'itlr_chunks') + '_active'
    try:
        return qdrant_name(alias)
    except ValueError:
        raise VersionError('Invalid Qdrant alias configuration') from None


def require_active_alias(store):
    aliases = store.request('GET', f'{store.path}/aliases')['aliases']
    if not any(entry.get('alias_name') == active_alias() for entry in aliases):
        raise VersionError('Qdrant alias and artifact pointer refer to different revisions')


def load_public_corpus(path):
    verify_integrity(path, required=True)
    if not probe_ok(path):
        raise VersionError('Only artifacts with a successful probe can be imported')
    version = hashlib.sha256((path / MANIFEST).read_bytes()).hexdigest()
    with (path / 'search_meta.pkl').open('rb') as stream:
        meta = pickle.load(stream)
    preset = PRESETS['e5-base']
    if any(meta.get(key) != preset[key] for key in ('model_name', 'query_prefix', 'passage_prefix')):
        raise ValueError('Qdrant migration requires the multilingual E5-base artifact preset')
    with (path / 'item_list.pkl').open('rb') as stream:
        catalog = pickle.load(stream).to_dict('records')
    with (path / 'chunk_meta.pkl').open('rb') as stream:
        rows = pickle.load(stream)['rows']
    with (path / 'chunk_embeddings.pkl').open('rb') as stream:
        vectors = FAISSVectorStore(pickle.load(stream))
    if vectors.dimension != preset['dim'] or vectors.size != len(rows):
        raise ValueError('Chunk vectors do not match the E5-base artifact dimensions')
    matrix = vectors.index.reconstruct_n(0, vectors.size)

    items = {int(row['item_id']): row for row in catalog}
    if len(items) != len(catalog) or {int(row['item_id']) for row in rows} != items.keys():
        raise ValueError('Invalid item ownership in chunk artifacts')
    payloads = []
    seen = set()
    for row in rows:
        item_id, chunk_idx = int(row['item_id']), int(row['chunk_idx'])
        item = items[item_id]
        origin, license_id = item['origin'], item['crawl_license']
        if (not isinstance(origin, str) or not origin.startswith('crawl:')
                or not isinstance(license_id, str) or not license_id.strip()
                or not isinstance(item['crawl_hash'], str)
                or not re.fullmatch(r'[0-9a-fA-F]{64}', item['crawl_hash'])):
            raise ValueError(f'Item {item_id} lacks approved crawler provenance')
        chunk_id = f'{item_id}:{chunk_idx}'
        if chunk_idx < 0 or chunk_id in seen or not row['chunk_text'].strip():
            raise ValueError('Invalid or duplicate chunk ID')
        seen.add(chunk_id)
        payloads.append({
            'item_id': item_id, 'chunk_id': chunk_id, 'source_id': origin.removeprefix('crawl:'),
            'origin': origin, 'language': item['crawl_lang'], 'license': license_id,
            'document_hash': item['crawl_hash'], 'content_hash': hashlib.sha256(row['chunk_text'].encode()).hexdigest(),
            'approval_state': 'approved', 'version': version,
        })
    return version, rows, matrix, payloads


def verify_collection(store, matrix, payloads):
    store.health()
    config_result = store.request('GET', store.path)
    schema = config_result['config']['params']['vectors'].get('dense', {})
    if schema.get('size') != store.dimension or schema.get('distance') != 'Dot':
        raise VersionError('Qdrant vector configuration mismatch')
    for start in range(0, store.size, 128):
        ids = range(start, min(start + 128, store.size))
        records = store.request('POST', f'{store.path}/points', {
            'ids': list(ids), 'with_payload': True, 'with_vector': ['dense'],
        })
        if {record['id'] for record in records} != set(ids) or len(records) != len(ids):
            raise VersionError('Qdrant point ownership mismatch')
        for record in records:
            idx = record['id']
            if (record['payload'] != payloads[idx]
                    or not np.array_equal(np.asarray(record['vector']['dense'], dtype=np.float32), matrix[idx])):
                raise VersionError('Qdrant point payload or vector mismatch')


def stage_collection(store, matrix, payloads):
    # PUT claims a new physical collection. On a repeat, verify the existing
    # collection byte-for-byte. Never rewrite an already named revision.
    try:
        store.request('PUT', store.path, {'vectors': {'dense': {'size': store.dimension, 'distance': 'Dot'}}})
    except QdrantUnavailable:
        verify_collection(store, matrix, payloads)
        return

    for field, kind in (
        ('item_id', 'integer'), ('chunk_id', 'keyword'), ('source_id', 'keyword'),
        ('language', 'keyword'), ('approval_state', 'keyword'), ('version', 'keyword'),
    ):
        store.request('PUT', f'{store.path}/index?wait=true', {'field_name': field, 'field_schema': kind})
    for start in range(0, store.size, 128):
        store.upsert_chunks([
            {'id': idx, 'vector': {'dense': matrix[idx].tolist()}, 'payload': payloads[idx]}
            for idx in range(start, min(start + 128, store.size))
        ])
    verify_collection(store, matrix, payloads)


def promote(store, alias):
    alias = qdrant_name(alias)
    aliases = store.request('GET', '/aliases')['aliases']
    previous = next((entry['collection_name'] for entry in aliases if entry['alias_name'] == alias), None)
    if previous == store.collection:
        return previous
    actions = [{'delete_alias': {'alias_name': alias}}] if previous else []
    actions.append({'create_alias': {'collection_name': store.collection, 'alias_name': alias}})
    store.request('POST', '/collections/aliases', {'actions': actions})
    return previous


def verify_parity_report(path, store):
    from itlr.retrieval.service import DEFAULT_SEARCH_MIN_PCT

    report = json.loads(path.read_text(encoding='utf-8'))
    paths = [config.ROOT / 'eval' / name for name in (
        'release_queries.jsonl', 'engineering_confirmation_queries.jsonl')]
    expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    cases = [json.loads(line)['id'] for p in paths for line in p.read_text(encoding='utf-8').splitlines()]
    observations = report.get('cases', [])
    if (report.get('manifest_sha256') != store.version or report.get('points') != store.size
            or report.get('min_pct') != DEFAULT_SEARCH_MIN_PCT or report.get('queries') != expected
            or report.get('rank_drift') != [] or [row['id'] for row in observations] != cases
            or any(row['faiss'] != row['qdrant'] for row in observations)):
        raise VersionError('A matching frozen parity report is required for promotion')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'verify', 'promote', 'snapshot'])
    parser.add_argument('--artifacts', type=Path, default=config.current_dir())
    parser.add_argument('--alias')
    parser.add_argument('--parity-report', type=Path)
    args = parser.parse_args()
    if args.action == 'promote' and args.parity_report is None:
        parser.error('promote requires --parity-report from eval.eval_qdrant_migration')
    version, rows, matrix, payloads = load_public_corpus(args.artifacts)
    store = version_store(version, len(rows), matrix.shape[1], writer=args.action != 'verify')
    if args.action == 'stage':
        stage_collection(store, matrix, payloads)
    else:
        verify_collection(store, matrix, payloads)
    print(f'{args.action}: {store.collection}, {store.size} verified points')
    if args.action == 'promote':
        verify_parity_report(args.parity_report, store)
        alias = args.alias or active_alias()
        print(f'{alias}: {promote(store, alias)} -> {store.collection}')
    if args.action == 'snapshot':
        print(store.request('POST', f'{store.path}/snapshots?wait=true')['name'])


if __name__ == '__main__':
    main()
