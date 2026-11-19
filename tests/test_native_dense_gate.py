import numpy as np

from eval.qdrant_native import NativeHybrid


class Store:
    path = '/collections/test'

    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def dense_search(self, vector, *, min_relevance):
        assert vector.shape == (1, 2)
        assert min_relevance == .84
        return self.scores

    def _filter(self):
        return {'must': [{'key': 'version', 'match': {'value': 'v1'}}]}

    def request(self, method, path, body):
        self.calls.append(body)
        return {'points': [{'id': 1, 'score': .03}]}


def test_native_gate_refuses_sparse_only_candidates():
    store = Store({0: .8399})
    index = NativeHybrid(store, [{'item_id': 1, 'chunk_idx': 0, 'chunk_text': 'password'}])
    assert index.search('password', np.array([1, 0]), min_relevance=.84, top_k=5,
                        unique_items=True, dense_gate=True) == []
    assert store.calls == []


def test_native_applies_dense_eligibility_before_sparse_truncation():
    store = Store({0: .8399, 1: .84})
    rows = [{'item_id': i, 'chunk_idx': 0, 'chunk_text': 'password database'} for i in (1, 2)]
    hits = NativeHybrid(store, rows).search('password', np.array([1, 0]), min_relevance=.84,
                                          top_k=5, unique_items=True, dense_gate=True)
    assert [hit['chunk_id'] for hit in hits] == ['2:0']
    for branch in store.calls[0]['prefetch']:
        assert branch['filter']['must'] == [
            {'key': 'version', 'match': {'value': 'v1'}}, {'has_id': [1]},
        ]
