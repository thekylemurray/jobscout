from datetime import datetime, timezone
from jobscout.models import Job
from jobscout.scoring import apply_freshness

def test_numeric_published_at_gets_age(config):
    # 2026-09-03 epoch; exact age is runtime-dependent, but it must parse.
    job=Job("1","Example","himalayas","SEO Manager","Remote - United States","Remote","Full time","SEO analytics","","",1788436800,"2026-09-03T12:00:00+00:00","")
    apply_freshness(job, config, board_initialized=True, is_new=False)
    assert job.age_hours is not None
