from jobscout.app import render_html
from jobscout.demo import demo_jobs

def test_dashboard_renders_explanations(config):
    page=render_html(demo_jobs(config))
    assert "Why these scores?" in page
    assert "Worth reviewing" in page or "Strong matches" in page
    assert "lane confidence" in page
