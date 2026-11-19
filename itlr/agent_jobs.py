"""Operator-only, PostgreSQL-backed ingestion and staged embedding queue."""
from __future__ import annotations

import argparse
from contextlib import suppress
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from itlr import config

LEASE_SECONDS = 45
HEARTBEAT_SECONDS = 10
JOB_TIMEOUT_SECONDS = 7200


def connect():
    url = os.environ.get('ITLR_JOB_DATABASE_URL')
    if not url:
        raise RuntimeError('ITLR_JOB_DATABASE_URL is required')
    return psycopg.connect(url, autocommit=True, connect_timeout=5, row_factory=dict_row,
                           options='-c statement_timeout=5000')


def enqueue(db, key, kind, max_attempts):
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
        raise ValueError('Missing or invalid job key')
    row = db.execute("""
        INSERT INTO agent_jobs (job_key, kind, max_attempts) VALUES (%s,%s,%s)
        ON CONFLICT (job_key) DO NOTHING RETURNING id, kind, max_attempts, state
    """, (key, kind, max_attempts)).fetchone()
    if row is None:
        row = db.execute('SELECT id, kind, max_attempts, state FROM agent_jobs WHERE job_key=%s',
                         (key,)).fetchone()
    if row is None or (row['kind'], row['max_attempts']) != (kind, max_attempts):
        raise ValueError('Job key already used with different settings')
    return row


def claim(db, lease_seconds=LEASE_SECONDS):
    db.execute("""
        UPDATE agent_jobs SET state='dead', claim_token=NULL, lease_until=NULL, updated_at=now()
        WHERE state='running' AND lease_until <= now() AND attempts >= max_attempts
    """)
    return db.execute("""
        WITH ready AS (
          SELECT id FROM agent_jobs
          WHERE attempts < max_attempts
            AND ((state='queued' AND available_at <= now())
                 OR (state='running' AND lease_until <= now()))
          ORDER BY available_at, id
          LIMIT 1 FOR UPDATE SKIP LOCKED
        )
        UPDATE agent_jobs j
        SET state='running', claim_token=%s, lease_until=now() + %s * interval '1 second',
            updated_at=now(), attempts=j.attempts + 1
        FROM ready WHERE j.id=ready.id
        RETURNING j.id,j.kind,j.attempts,j.claim_token
    """, (uuid4(), lease_seconds)).fetchone()


def heartbeat(db, job):
    return db.execute("""
        UPDATE agent_jobs SET lease_until=now() + %s * interval '1 second', updated_at=now()
        WHERE id=%s AND claim_token=%s AND state='running' AND lease_until>now()
    """, (LEASE_SECONDS, job['id'], job['claim_token'])).rowcount == 1


def retry_delay(attempts):
    return min(300, 10 * 2 ** min(5, attempts - 1))


def finish(db, job, exit_code):
    return db.execute("""
        UPDATE agent_jobs SET state=CASE WHEN %s=0 THEN 'succeeded'
                                         WHEN attempts>=max_attempts THEN 'dead'
                                         ELSE 'queued' END,
          exit_code=%s, available_at=now() + %s * interval '1 second',
          claim_token=NULL, lease_until=NULL, updated_at=now()
        WHERE id=%s AND claim_token=%s AND state='running' AND lease_until>now()
    """, (exit_code, exit_code, retry_delay(job['attempts']),
          job['id'], job['claim_token'])).rowcount == 1


def job_command(kind, sources=None):
    if kind == 'ingest':
        return [sys.executable, 'scripts/collect_data.py', *(['--sources', sources] if sources else [])]
    if kind == 'embed':
        return [sys.executable, 'scripts/build_all_v2.py', '--real-only', '--no-activate']
    raise ValueError('Invalid job kind')


def run_job(db, job, env):
    command = job_command(job['kind'], env.get('ITLR_JOB_INGEST_SOURCES'))
    if job['kind'] == 'embed' and env.get('ITLR_JOB_MAX_ITEMS'):
        command += ['--max-items', str(int(env['ITLR_JOB_MAX_ITEMS']))]
    try:
        child = subprocess.Popen(command, cwd=config.ROOT, env=env, start_new_session=True)
    except OSError:
        return 126
    end = time.monotonic() + JOB_TIMEOUT_SECONDS
    try:
        while time.monotonic() < end:
            try:
                return child.wait(HEARTBEAT_SECONDS)
            except subprocess.TimeoutExpired:
                if not heartbeat(db, job):
                    return None
        return 124
    finally:
        if child.poll() is None:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(5)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait()


def worker_env():
    raw = os.environ.get('ITLR_JOB_STAGING_ROOT')
    if not raw:
        raise RuntimeError('ITLR_JOB_STAGING_ROOT is required')
    stage = Path(raw).resolve()
    data = stage / 'data'
    artifacts = stage / 'artifacts'
    data.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    if data.resolve() == config.DATA_DIR.resolve() or artifacts.resolve() == config.ARTIFACTS_DIR.resolve():
        raise RuntimeError('Job staging must be distinct from the configured serving paths')
    job_env = dict(os.environ)
    for name in ('DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'DEEPSEEK_API_KEY_FILE', 'OPENAI_API_KEY_FILE',
                 'ITLR_JOB_DATABASE_URL',
                 'ITLR_ITEMS_CSV', 'ITLR_INTERACTIONS_CSV', 'DATABASE_URL', 'JWT_SECRET',
                 'ITLR_ADMIN_TOKEN', 'ITLR_CHAT_PRINCIPAL_KEY', 'ITLR_QDRANT_WRITE_KEY',
                 'ITLR_QDRANT_API_KEY'):
        job_env.pop(name, None)
    job_env.update(ITLR_DATA_DIR=str(data), ITLR_ARTIFACTS_DIR=str(artifacts),
                   ITLR_VECTOR_BACKEND='faiss', USE_OLLAMA='0', LLM_PROVIDER='none')
    return job_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    queue = sub.add_parser('enqueue')
    queue.add_argument('kind', choices=['ingest', 'embed'])
    queue.add_argument('key')
    queue.add_argument('--max-attempts', type=int, choices=range(1, 11), default=3)
    worker = sub.add_parser('worker')
    worker.add_argument('--once', action='store_true')
    sub.add_parser('dead-letter')
    args = parser.parse_args()

    with connect() as db:
        if args.action == 'enqueue':
            print(json.dumps(enqueue(db, args.key, args.kind, args.max_attempts)))
            return 0
        if args.action == 'dead-letter':
            data = db.execute("""
                SELECT id, job_key, kind, attempts, exit_code, updated_at
                FROM agent_jobs WHERE state='dead' ORDER BY updated_at DESC LIMIT 100
            """).fetchall()
            print(json.dumps(data, default=str))
            return 0
        env = worker_env()
        while True:
            job = claim(db)
            if job is not None:
                status = run_job(db, job, env)
                if status is None or not finish(db, job, status):
                    print(f'Job {job["id"]} lease lost; outcome not committed', flush=True)
                else:
                    print(f'Job {job["id"]} attempt {job["attempts"]} exit {status}', flush=True)
                if args.once:
                    return 1 if status is None else status
            elif not args.once:
                time.sleep(1)
            if args.once:
                return 0


if __name__ == '__main__':
    def stop(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
