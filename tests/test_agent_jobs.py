from itlr.agent_jobs import job_command, retry_delay


def test_jobs_run_only_existing_staging_pipeline_with_bounded_backoff():
    assert job_command('embed')[-2:] == ['--real-only', '--no-activate']
    assert job_command('ingest', sources='mdn-blog')[-2:] == ['--sources', 'mdn-blog']
    assert retry_delay(1) == 10
    assert retry_delay(2) == 20
    assert retry_delay(20) == 300
