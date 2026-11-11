from types import SimpleNamespace


def test_crashing_job_stops_but_waiting_job_does_not_spend_a_retry(monkeypatch):
    from app import jobs
    rows = [SimpleNamespace(id='crash', status='RUNNING', stage='REVIEWING',
                            summary={'resubmitted_after_restart': 2}, error=None),
            SimpleNamespace(id='waiting', status='QUEUED', stage='QUEUED',
                            summary={'resubmitted_after_restart': 2}, error=None)]
    class DB:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def query(self, *args): return self
        def filter(self, *args): return self
        def all(self): return rows
        def commit(self): pass
    submitted, settled = [], []
    monkeypatch.setattr(jobs, 'SessionLocal', DB)
    monkeypatch.setattr(jobs, 'submit', submitted.append)
    monkeypatch.setattr(jobs, '_settle_credits', settled.append)
    assert jobs.resubmit_unfinished() == 1
    assert submitted == ['waiting'] and settled == ['crash']
    assert rows[0].status == 'FAILED' and rows[0].finished_at
    assert 'omstarter' in rows[0].error
    assert rows[1].summary['resubmitted_after_restart'] == 2


def test_a_large_set_gets_more_time_than_a_single_sheet_but_never_without_end(monkeypatch):
    from app import jobs
    from app.config import settings
    monkeypatch.setattr(settings, "analysis_deadline_s", 7200)
    monkeypatch.setattr(settings, "analysis_deadline_per_page_s", 900)
    monkeypatch.setattr(settings, "analysis_deadline_max_s", 6 * 3600)
    assert jobs.deadline_for(1) == 7200 and jobs.deadline_for(None) == 7200     # minst två timmar
    assert jobs.deadline_for(12) == 12 * 900                                     # tre timmar för tolv blad
    assert jobs.deadline_for(400) == 6 * 3600                                    # aldrig över taket
