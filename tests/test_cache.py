from redis.exceptions import ConnectionError

from itlr.retrieval.cache import PublicCache


class Unavailable:
    def get(self, _):
        raise ConnectionError('private Redis endpoint')


def test_cache_isolation_by_revision_configuration_and_operation():
    cache = PublicCache(None, 'deployment', 'revision1', 'E5')
    other = PublicCache(None, 'deployment', 'revision2', 'E5')
    assert 'personal input' not in cache.key('embedding', ['personal input'])
    assert cache.key('embedding', ['personal input']) != cache.key('retrieval', ['personal input'])
    assert cache.key('retrieval', ['q', .84]) != cache.key('retrieval', ['q', .90])
    assert cache.key('retrieval', ['q', .84]) != other.key('retrieval', ['q', .84])


def test_cache_outage_runs_read_once():
    calls = []
    cache = PublicCache(Unavailable(), 'deployment', 'revision1', 'E5')

    def load():
        calls.append(1)
        return ['public']

    assert cache.read('retrieval', ['q'], load) == ['public']
    assert calls == [1]


def test_healthy_contended_cache_never_duplicates_expensive_loader(monkeypatch):
    import pytest
    from itlr.retrieval import cache as module

    class Busy:
        def get(self, _):
            return None

        def set(self, *args, **kwargs):
            return None

    now = [0.]
    monkeypatch.setattr(module, 'monotonic', lambda: now[0])

    def advance(seconds):
        now[0] += seconds

    monkeypatch.setattr(module, 'sleep', advance)
    cache = PublicCache(Busy(), 'deployment', 'revision1', 'E5')
    with pytest.raises(RuntimeError, match='cache fill is busy'):
        cache.read('retrieval', ['q'], lambda: pytest.fail('duplicate expensive loader'))


def test_epoch_change_invalidates_every_public_layer(monkeypatch):
    cache = PublicCache(None, 'deployment', 'revision1', 'E5')
    first = cache.key('response', ['Docker'])
    monkeypatch.setenv('ITLR_CACHE_EPOCH', 'new')
    assert cache.key('response', ['Docker']) != first
