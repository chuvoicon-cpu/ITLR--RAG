import httpx
import numpy as np
import pytest

from itlr.core.chunks import ChunkIndex
from itlr.retrieval.vector_store import FAISSVectorStore, QdrantUnavailable, QdrantVectorStore


def test_dense_adapter_preserves_sparse_gate_and_evidence():
    rows = [{'item_id': 1, 'chunk_idx': 0, 'chunk_text': 'exact identifier ABC123'},
            {'item_id': 2, 'chunk_idx': 0, 'chunk_text': 'semantic result'}]
    store = FAISSVectorStore(np.eye(2, dtype=np.float32))
    index = ChunkIndex(rows, dense_store=store)
    assert [r['chunk_id'] for r in index.search('ABC123', [0, 1], min_relevance=.84)] == ['2:0']
    assert index.search('ABC123', [0, 1], allowed_item_ids={1})[0]['excerpt'] == rows[0]['chunk_text']


def test_qdrant_dense_transport_and_health():
    def respond(request):
        assert request.headers['api-key'] == 'test-reader'
        if request.url.path.endswith('/points/query'):
            import json
            body = json.loads(request.content)
            assert body['params'] == {'exact': True}
            assert body['using'] == 'dense'
            assert body['filter']['must'] == [
                {'key': 'version', 'match': {'value': 'revision'}},
                {'key': 'approval_state', 'match': {'value': 'approved'}},
            ]
            return httpx.Response(200, json={'result': {'points': [{'id': 0, 'score': 1.00000001}]}})
        if request.url.path.endswith('/points/count'):
            return httpx.Response(200, json={'result': {'count': 2}})
        return httpx.Response(503)

    store = QdrantVectorStore('http://qdrant', 'test_chunks', 'revision', 2, 2,
                              api_key='test-reader', transport=httpx.MockTransport(respond))
    assert store.dense_search(np.array([[1, 0]], dtype=np.float32), min_relevance=.84) == {0: 1.0}
    store.health()
    with pytest.raises(QdrantUnavailable, match='Qdrant request failed') as error:
        store.request('GET', '/error')
    assert 'test-reader' not in str(error.value)
    assert error.value.__cause__ is None
