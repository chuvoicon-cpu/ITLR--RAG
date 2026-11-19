"""Dense backend contract used by the shared BM25/RRF pipeline."""
from __future__ import annotations

import re
from typing import Protocol
from weakref import finalize

import httpx
import numpy as np

from itlr.versioning import VersionError


class VectorStore(Protocol):
    dimension: int
    size: int

    def dense_search(self, vector: np.ndarray, *, min_relevance: float) -> dict[int, float]:
        """Map artifact row IDs to cosine scores. The query is L2-normalized."""
        ...

    def health(self) -> None: ...


class FAISSVectorStore:
    def __init__(self, vectors):
        import faiss

        vectors = np.asarray(vectors, dtype='float32')
        if vectors.ndim != 2 or not vectors.size or not np.isfinite(vectors).all():
            raise ValueError('Invalid chunk vectors or ownership')
        norms = np.linalg.norm(vectors, axis=1)
        if not np.isfinite(norms).all() or np.any(norms == 0):
            raise ValueError('Invalid chunk vectors or ownership')
        self.size, self.dimension = vectors.shape
        vectors = vectors.copy()
        faiss.normalize_L2(vectors)
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(vectors)

    def dense_search(self, vector, *, min_relevance):
        scores, ids = self.index.search(vector, self.size)
        return dict(zip(ids[0].tolist(), np.clip(scores[0], -1., 1.).tolist()))

    def health(self):
        if self.index.ntotal != self.size:
            raise VersionError('FAISS point count mismatch')


class QdrantUnavailable(VersionError):
    """Qdrant could not serve the artifact revision safely."""


def qdrant_name(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', value):
        raise ValueError('Invalid Qdrant collection or alias name')
    return value


class QdrantVectorStore:
    """Exact dense search pinned to an immutable public knowledge collection."""

    def __init__(self, url, collection, version, dimension, size, *, api_key=None, transport=None):
        endpoint = httpx.URL(url)
        if (endpoint.scheme not in ('http', 'https') or not endpoint.host
                or endpoint.userinfo or endpoint.path not in ('', '/')
                or endpoint.query or endpoint.fragment):
            raise ValueError('Invalid Qdrant URL')
        self.url = endpoint
        self.collection = qdrant_name(collection)
        self.path = f'/collections/{self.collection}'
        self.version = version
        self.dimension = dimension
        self.size = size
        self.headers = {'api-key': api_key} if api_key else {}

        self._http = httpx.Client(base_url=self.url, headers=self.headers, timeout=5,
                                  trust_env=False, transport=transport)
        # Old engines stay alive while requests still hold them during a reload.
        # Close idle connections when the store's last owner releases it.
        self._close = finalize(self, self._http.close)

    def request(self, method, path, body=None, **kwargs):
        try:
            response = self._http.request(method, path, json=body, **kwargs)
            response.raise_for_status()
            return response.json()['result']
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise QdrantUnavailable('Qdrant request failed') from None

    def _filter(self, metadata=None):
        fields = {**(metadata or {}), 'version': self.version, 'approval_state': 'approved'}
        return {'must': [{'key': key, 'match': {'value': value}} for key, value in fields.items()]}

    def dense_search(self, vector, *, min_relevance, metadata=None):
        body = {
            'query': vector[0].tolist(), 'using': 'dense', 'params': {'exact': True},
            'filter': self._filter(metadata), 'limit': self.size, 'with_payload': False,
        }
        # Leave a float32 margin here. ChunkIndex applies the historical floor.
        if min_relevance > -1:
            body['score_threshold'] = min_relevance - 2e-6
        result = self.request('POST', f'{self.path}/points/query', body)
        dense_scores = {}
        try:
            for hit in result['points']:
                idx, score = hit['id'], hit['score']
                if (type(idx) is not int or not 0 <= idx < self.size or idx in dense_scores
                        or not np.isfinite(score)):
                    raise ValueError
                dense_scores[idx] = max(-1., min(1., float(score)))
        except (TypeError, ValueError, KeyError):
            raise QdrantUnavailable('Malformed Qdrant dense results') from None
        if min_relevance <= -1 and metadata is None and len(dense_scores) != self.size:
            raise QdrantUnavailable('Qdrant dense results incomplete')
        return dense_scores

    def health(self):
        result = self.request('POST', f'{self.path}/points/count',
                              {'filter': self._filter(), 'exact': True})
        if not isinstance(result, dict) or result.get('count') != self.size:
            raise QdrantUnavailable('Qdrant version or point count mismatch')

    def upsert_chunks(self, points):
        """Offline writers can insert or fully replace points in their staging collection."""
        if any(point['payload'].get('version') != self.version for point in points):
            raise ValueError('Cannot upsert chunks from another revision')
        self.request('PUT', f'{self.path}/points?wait=true', {'points': points})

    def delete_document(self, item_id):
        """Offline staging only. Publish a new revision to propagate a deletion."""
        if type(item_id) is not int:
            raise ValueError('Invalid item ID')
        self.request('POST', f'{self.path}/points/delete?wait=true',
                     {'filter': self._filter({'item_id': item_id})})

    def exact_chunk(self, chunk_id):
        result = self.request('POST', f'{self.path}/points/scroll', {
            'filter': self._filter({'chunk_id': chunk_id}), 'limit': 2,
            'with_payload': True, 'with_vector': False,
        })
        points = result['points']
        if len(points) > 1:
            raise QdrantUnavailable('Duplicate Qdrant chunk identity')
        return points[0]['payload'] if points else None
