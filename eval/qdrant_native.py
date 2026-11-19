"""Experimental phase B. Separate collection and independent dense/sparse candidates."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from itlr.core.recommender import tokenize
from itlr.retrieval.bm25 import BM25Index
from itlr.retrieval.vector_store import QdrantUnavailable, QdrantVectorStore


class NativeHybrid:
    def __init__(self, store, rows):
        self.store = store
        self.rows = rows
        self.bm25 = BM25Index().fit([row['chunk_text'] for row in rows])
        self.terms = {word: idx for idx, word in enumerate(sorted(self.bm25.idf))}

    def stage(self, matrix, payloads):
        store = self.store
        try:
            store.request('PUT', store.path, {
                'vectors': {'dense': {'size': store.dimension, 'distance': 'Dot'}},
                'sparse_vectors': {'bm25': {}},
            })
        except QdrantUnavailable:
            store.health()
            return
        for first in range(0, store.size, 128):
            points = []
            for idx in range(first, min(first + 128, store.size)):
                tf = self.bm25.doc_freqs[idx]
                dl = self.bm25.doc_lengths[idx]
                k = self.bm25.k1 * (1 - self.bm25.b + self.bm25.b * dl / max(self.bm25.avgdl, 1))
                tokens = sorted(tf, key=self.terms.__getitem__)
                vector = {'dense': matrix[idx].tolist()}
                if tokens:
                    vector['bm25'] = {
                        'indices': [self.terms[term] for term in tokens],
                        'values': [tf[term] * (self.bm25.k1 + 1) / (tf[term] + k) for term in tokens],
                    }
                points.append({'id': idx, 'vector': vector, 'payload': payloads[idx]})
            store.upsert_chunks(points)
        store.health()

    def branches(self, query, vector, *, min_relevance, candidate_k, eligible_ids=None):
        tokens = sorted(set(tokenize(query)) & self.terms.keys(), key=self.terms.__getitem__)
        filt = self.store._filter()
        if eligible_ids is not None:
            filt["must"].append({"has_id": sorted(eligible_ids)})
        prefetch = [{
            'query': vector.tolist(), 'using': 'dense', 'params': {'exact': True}, 'filter': filt,
            'limit': candidate_k, 'score_threshold': min_relevance - 1e-6,
        }]
        if tokens:
            prefetch.append({
                'query': {'indices': [self.terms[t] for t in tokens],
                          'values': [self.bm25.idf[t] for t in tokens]},
                'using': 'bm25', 'filter': filt, 'limit': candidate_k,
            })
        return prefetch

    def search(self, query, vector, *, min_relevance, top_k, unique_items, candidate_k=32, dense_gate=False):
        eligible_ids = None
        if dense_gate:
            scores = self.store.dense_search(vector.reshape(1, -1), min_relevance=min_relevance)
            eligible_ids = {idx for idx, score in scores.items() if score + 1e-6 >= min_relevance}
            if not eligible_ids:
                return []
        branches = self.branches(query, vector, min_relevance=min_relevance, candidate_k=candidate_k,
                                 eligible_ids=eligible_ids)
        result = self.store.request('POST', f'{self.store.path}/points/query', {
            'prefetch': branches, 'query': {'rrf': {'k': 61}},
            'limit': candidate_k, 'with_payload': False,
        })
        hits, seen = [], set()
        for point in result['points']:
            if eligible_ids is not None and point['id'] not in eligible_ids:
                raise QdrantUnavailable('Native fusion returned a point outside the evidence gate')
            row = self.rows[point['id']]
            item_id = int(row['item_id'])
            if unique_items and item_id in seen:
                continue
            seen.add(item_id)
            hits.append({**row, 'chunk_id': f"{item_id}:{row['chunk_idx']}"})
            if len(hits) == top_k:
                break
        return hits


def build_native(base, rows, matrix, payloads):
    store = QdrantVectorStore(base.url, f'{base.collection}_native_bm25_v1', base.version,
                              base.dimension, base.size, api_key=base.headers.get('api-key'))
    hybrid = NativeHybrid(store, rows)
    hybrid.stage(matrix, payloads)
    return hybrid
