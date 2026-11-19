"""Create disposable users and exercise agent tools through real auth, CSRF and PostgreSQL."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4

import httpx


@contextmanager
def register(base, email=None):
    with httpx.Client(base_url=base, timeout=25, trust_env=False) as client:
        client.get('/register').raise_for_status()
        result = client.post('/register', headers={'X-CSRF-Token': client.cookies['csrf']}, data={
            'name': 'Agent staging test', 'email': email or f'test-{uuid4().hex}@example.org',
            'password': 'AgentStaging9!' + uuid4().hex,
        })
        assert result.status_code == 302, result.status_code
        yield client


def agent(client, tool, args, *, csrf=True):
    return client.post('/api/agent/tools', headers={'X-CSRF-Token': client.cookies['csrf']} if csrf else {},
                       json={'tool': tool, 'args': args})


def check(web, api, *, strict_chat=False, support_db=False):
    with httpx.Client(base_url=api, timeout=20, trust_env=False) as knowledge:
        health = knowledge.get('/health').raise_for_status().json()
        assert health['artifacts']['vector_backend'] == 'qdrant'
        assert health['items'] == 118
        search = {'query': 'Docker', 'min_pct': 84}
        first = knowledge.post('/api/search', json=search).raise_for_status()
        second = knowledge.post('/api/search', json=search).raise_for_status()
        assert first.json() == second.json() and first.json()['results']
        assert first.headers['X-Request-ID'] != second.headers['X-Request-ID']
        direct = knowledge.post('/api/chat/stream', json={'message': 'Xin chào'},
                                headers={'X-ITLR-Principal': 'forged'} if strict_chat else {})
        if strict_chat:
            assert direct.status_code == 401
        else:
            events = direct.raise_for_status().text
            assert '"type": "final"' in events and '"type": "done"' in events

    with register(web) as owner, register(web) as peer:
        web_events = owner.post('/api/chat/stream', headers={'X-CSRF-Token': owner.cookies['csrf']},
                                json={'message': 'Xin chào'}).raise_for_status().text
        assert '"type":"final"' in web_events and '"type":"done"' in web_events
        assert agent(owner, 'get_user_progress', {}, csrf=False).status_code == 403
        assert agent(owner, 'get_user_progress', {'user_id': 1}).status_code == 400
        assert agent(owner, 'get_user_progress', {}).raise_for_status().json()['result'] == []
        owner.post('/api/save', headers={'X-CSRF-Token': owner.cookies['csrf']},
                   json={'course_id': 5001, 'status': 'in_progress', 'progress': 25}).raise_for_status()
        assert agent(owner, 'get_user_progress', {}).raise_for_status().json()['result'] == [
            {'course_id': 5001, 'status': 'in_progress', 'progress': 25}
        ]
        assert agent(peer, 'get_user_progress', {}).raise_for_status().json()['result'] == []
        course = agent(owner, 'get_course_details', {'item_id': 5001}).raise_for_status().json()
        assert course['result']['item_id'] == 5001
        assert agent(owner, 'search_knowledge', {'query': 'Docker'}).raise_for_status().json()['result']

        proposed = agent(owner, 'create_learning_plan', {'track': 'python'}).raise_for_status().json()['result']
        assert len(proposed['plan']['steps']) == 3
        assert any(step['resources'] for step in proposed['plan']['steps'])
        args = {'confirm': True, 'track': 'python', 'preview_hash': proposed['hash'],
                'idempotency_key': uuid4().hex}
        assert agent(owner, 'save_learning_plan', {**args, 'confirm': False}).status_code == 400
        with ThreadPoolExecutor(max_workers=2) as pool:
            saved = list(pool.map(lambda _: agent(owner, 'save_learning_plan', args), range(2)))
        assert all(response.status_code == 200 for response in saved), [response.status_code for response in saved]
        assert saved[0].json() == saved[1].json()
        assert agent(owner, 'save_learning_plan', {**args, 'preview_hash': 'a' * 64}).status_code == 409
        copy = agent(peer, 'save_learning_plan', args).raise_for_status().json()
        assert copy['result']['saved_at'] != saved[0].json()['result']['saved_at']
        assert agent(owner, 'handoff_to_human', {}).status_code == 400
        handoff = {'confirm': True, 'detail': 'Disposable support ticket', 'idempotency_key': uuid4().hex}
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(lambda _: agent(owner, 'handoff_to_human', handoff), range(2)))
        assert all(r.status_code == 202 for r in receipts)
        ticket = receipts[0].json()['result']
        assert ticket == receipts[1].json()['result']
        assert agent(owner, 'handoff_to_human', {**handoff, 'detail': 'Different issue'}).status_code == 409
        assert owner.get('/api/agent/handoffs').status_code == 403
        if support_db:
            from itlr.agent_jobs import connect

            email = f'support-{uuid4().hex}@example.org'
            with connect() as db, register(web, email=email) as support:
                database = db.execute('SELECT current_database() AS name').fetchone()['name']
                if database != 'itlr_agent_hardening' and not database.endswith('_test'):
                    raise RuntimeError('Support verification requires a disposable test database')
                # Only the disposable, freshly registered fixture account is promoted.
                row = db.execute(
                    "UPDATE users SET role='admin' WHERE email=%s RETURNING id", (email,)).fetchone()
                tickets = support.get('/api/agent/handoffs').raise_for_status().json()['tickets']
                assert any(r['id'] == ticket['id'] for r in tickets)
                path = f"/api/agent/handoffs/{ticket['id']}/resolve"
                headers = {'X-CSRF-Token': support.cookies['csrf']}
                receipt = support.post(path, headers=headers).raise_for_status().json()['result']
                assert receipt['status'] == 'resolved'
                assert support.post(path, headers=headers).raise_for_status().json()['result'] == receipt
                audit = db.execute('SELECT resolved_by,resolve_request_id FROM agent_handoffs WHERE id=%s',
                                   (ticket['id'],)).fetchone()
                assert audit['resolved_by'] == row['id'] and audit['resolve_request_id'] is not None

    print('Agent HTTP e2e: health, correlated search, SSE final/done, CSRF, real course/search, ownership,')
    print('plan preview/approval, two concurrent idempotent saves, cross-user idempotency isolation, handoff confirmation/replay/conflict and support role PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web', required=True)
    parser.add_argument('--api', required=True)
    parser.add_argument('--strict-chat', action='store_true')
    parser.add_argument('--support-db', action='store_true',
                        help='Use ITLR_JOB_DATABASE_URL to provision one support account in a disposable database')
    args = parser.parse_args()
    check(args.web, args.api, strict_chat=args.strict_chat, support_db=args.support_db)
