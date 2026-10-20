import pytest

from jobscout.profile_signals import credential_review_text, labeled_full_time_pay, skill_signals


def test_equivalences_award_each_configured_category_once():
    hits = skill_signals('Budgets and budgeting. Vendor oversight, managing CROs and vendor management. Global clinical trials. Phase III and phase 3.',
                         ['budget', 'budgeting', 'vendor management', 'CRO oversight', 'global trials', 'phase III', 'phase 3'])
    assert set(hits) == {'budget', 'vendor management', 'global trials', 'phase 3'}


def test_equivalences_do_not_invent_unconfigured_skills():
    assert skill_signals('Budgeting, managing CROs, global clinical trials.', ['French']) == {}
    assert skill_signals('French and Python', ['French', 'Python']) == {'french': 'French', 'python': 'Python'}


def test_md_location_is_not_medical_degree():
    text = credential_review_text('Rockville, MD. MD or PhD preferred.')
    assert text == '. MD or PhD preferred.'


def test_fulltime_labeled_pay_keeps_inference_visible():
    result = labeled_full_time_pay('Pay Range: $160,000-$180,000 USD Benefits: medical.', 'Full time')
    assert '160000-180000' in result and 'period inferred' in result


@pytest.mark.parametrize('text, employment', [
    ('Pay Range: $160,000-$180,000 USD per month', 'Full time'),
    ('Total Pay Range: $160,000-$180,000 USD', 'Full time'),
    ('Pay Range: $160,000-$180,000 CAD', 'Full time'),
    ('Pay Range: $160,000-$180,000 USD', 'Contract'),
    ('Budget: $160,000-$180,000 USD', 'Full time'),
])
def test_ambiguous_pay_is_not_annualized(text, employment):
    assert labeled_full_time_pay(text, employment) == ''
