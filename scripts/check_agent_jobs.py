"""Exercise parallel claims, lease expiry, retry and fencing in a disposable database."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from itlr.agent_jobs import claim, connect, enqueue, finish, heartbeat


def one_claim():
    with connect() as db:
        return claim(db)


def main():
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM agent_jobs').fetchone()['n'] == 0
        key = uuid4().hex
        job = enqueue(db, key, 'ingest', 2)
        assert enqueue(db, key, 'ingest', 2) == job
        try:
            enqueue(db, key, 'embed', 2)
        except ValueError:
            pass
        else:
            raise AssertionError('Conflicting job key accepted')
        with ThreadPoolExecutor(max_workers=4) as workers:
            claimed = [r for r in workers.map(lambda _: one_claim(), range(4)) if r is not None]
        assert len(claimed) == 1, claimed
        first = claimed[0]
        assert first['id'] == job['id'] and first['attempts'] == 1 and heartbeat(db, first)
        db.execute("UPDATE agent_jobs SET lease_until=now() - interval '1 second' WHERE id=%s", (first['id'],))
        second = claim(db)
        assert second['id'] == first['id'] and second['attempts'] == 2
        assert not finish(db, first, 0) and not heartbeat(db, first)
        assert finish(db, second, 1) and claim(db) is None
        dead = db.execute('SELECT state, exit_code FROM agent_jobs WHERE id=%s', (first['id'],)).fetchone()
        assert dead == {'state': 'dead', 'exit_code': 1}

        queued = enqueue(db, uuid4().hex, 'embed', 2)
        assert finish(db, claim(db), 2)
        assert claim(db) is None
        db.execute("UPDATE agent_jobs SET available_at=now() WHERE id=%s", (queued['id'],))
        retried = claim(db)
        assert retried['attempts'] == 2 and finish(db, retried, 0)
        print('PostgreSQL: unique enqueue, 4 parallel claims, expiry/reclaim, stale fencing, backoff and dead letter PASS')


if __name__ == '__main__':
    main()
