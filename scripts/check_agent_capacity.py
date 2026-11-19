"""Real Redis cluster-admission and breaker checks in a random disposable namespace."""
from __future__ import annotations

import multiprocessing as mp
import os
from time import sleep
from uuid import uuid4

from fastapi import HTTPException

from itlr.api.ratelimit import acquire_chat_slot
from itlr.chatbot.provider_budget import ProviderBudgetError, check_circuit, circuit_failure


def contender(results, release_event):
    try:
        release = acquire_chat_slot()
    except HTTPException as error:
        results.put(error.status_code)
        return
    try:
        results.put(200)
        if not release_event.wait(15):
            raise RuntimeError('integration harness did not release permit')
    finally:
        release()


def main():
    os.environ['ITLR_CACHE_NAMESPACE'] = 'capacity-check-' + uuid4().hex
    os.environ['ITLR_CHAT_CLUSTER_CONCURRENCY'] = '2'
    os.environ['ITLR_CHAT_CONCURRENCY'] = '0'
    ctx = mp.get_context('spawn')
    results = ctx.Queue()
    release_event = ctx.Event()
    workers = [ctx.Process(target=contender, args=(results, release_event)) for _ in range(6)]
    for worker in workers:
        worker.start()
    try:
        codes = [results.get(timeout=10) for _ in workers]
        assert codes.count(200) == 2 and codes.count(429) == 4, codes
    finally:
        release_event.set()
        for worker in workers:
            worker.join(10)
            if worker.is_alive():
                worker.terminate()
            assert worker.exitcode == 0
    acquire_chat_slot()()

    os.environ['ITLR_LLM_CIRCUIT_THRESHOLD'] = '2'
    os.environ['ITLR_LLM_CIRCUIT_SECONDS'] = '2'
    check_circuit('local-integration')
    circuit_failure('local-integration', TimeoutError('injected control-plane failure'))
    check_circuit('local-integration')
    circuit_failure('local-integration', TimeoutError('injected control-plane failure'))
    try:
        check_circuit('local-integration')
    except ProviderBudgetError as exc:
        assert str(exc) == 'Provider circuit is open'
    else:
        raise AssertionError('Circuit did not open')
    check_circuit('independent-provider')
    sleep(2.2)
    check_circuit('local-integration')
    print('Redis: 6 independent processes, 2 slots accepted, 4 denied, release/reuse; breaker opens and expires PASS')


if __name__ == '__main__':
    main()
