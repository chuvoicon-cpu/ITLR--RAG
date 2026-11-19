"""Shared chunk retrieval contract for search, chat and relevance gating."""
import hashlib

import numpy as np

from itlr.core.embeddings import encode_query
from itlr.retrieval.cache import public_query

DEFAULT_SEARCH_MIN_PCT = 84


class RetrievalService:
    def __init__(self, index, items, encoder, query_prefix='', reranker=None, cache=None):
        self.index = index
        self.encoder = encoder
        self.query_prefix = query_prefix
        self.reranker = reranker
        self.cache = cache
        self.items = {int(r['item_id']): r for r in items.to_dict('records')}

    def vector(self, query):
        def encode():
            return encode_query(self.encoder, query, {'query_prefix': self.query_prefix})

        if self.cache is None or not public_query(query):
            return encode()
        cached = self.cache.read('embedding', [self.query_prefix, query], lambda: encode().tolist())
        vector = np.asarray(cached, dtype=np.float32)
        if vector.shape != (self.index.dense_store.dimension,) or not np.isfinite(vector).all() or not np.linalg.norm(vector):
            return encode()
        return vector

    def relevance(self, query, vector=None):
        if not query.strip():
            return 0.
        hits = self.index.search('', vector if vector is not None else self.vector(query),
                                 top_k=1, candidate_k=1)
        return hits[0]['dense_score'] if hits else 0.

    def search(self, query, *, top_k=8, item_type=None, min_relevance=0., use_reranker=True,
               unique_items=False, vector=None):
        if not query.strip():
            return []
        allowed = {iid for iid,r in self.items.items() if not item_type or r['type']==item_type}
        def retrieve():
            return self.index.search(query, vector if vector is not None else self.vector(query),
                                     top_k=top_k, allowed_item_ids=allowed,
                                     min_relevance=min_relevance, unique_items=unique_items,
                                     reranker=self.reranker if use_reranker else None)

        if self.cache is not None and self.reranker is None and public_query(query):
            vector_key = (hashlib.sha256(np.asarray(vector, dtype=np.float32).tobytes()).hexdigest()
                          if vector is not None else None)
            hits = self.cache.read('retrieval', [query, top_k, item_type, min_relevance, unique_items, vector_key],
                                   retrieve)
        else:
            hits = retrieve()
        return [{**h,'item':self.items[int(h['item_id'])]} for h in hits]
