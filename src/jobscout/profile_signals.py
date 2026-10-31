"""Auditable equivalences for portable profiles; one award per configured category."""
import re

from .utils import has_term

GROUPS = {
    'budget': ('budget', r'\bbudget(?:s|ing)?\b|\bfinancial management\b'),
    'vendor management': ('vendor management', r'\bvendor (?:management|oversight)\b|\bCRO (?:management|oversight)\b|\bmanag(?:e|es|ing|ement of) (?:CROs?|external vendors)\b'),
    'line management': ('people leadership', r'\bline management\b|\bpersonnel leadership\b|\b(?:leading|managing|manage) (?:global )?teams\b|\bmanaging (?:CRAs|monitors)\b|\b(?:direct|indirect) supervisory experience\b'),
    'stakeholder management': ('stakeholder management', r'\bstakeholder (?:management|engagement)\b|\bmanag(?:e|ing) stakeholder relationships\b'),
    'global trials': ('global trials', r'\bglobal (?:clinical )?(?:trials|studies|study teams?)\b|\binternational clinical trials\b'),
    'vaccines': ('vaccines', r'\bvaccines?\b|\bvaccination\b'),
    'infectious disease': ('infectious disease', r'\binfectious diseases?\b'),
}
# Additional transferable operations terms. Use one award per conceptual category.
# These aliases work across marketing, business operations and PMO career lanes.
GENERAL_OPERATIONS = {
    "cross-functional leadership": r"\bcross[ -]functional\b.{0,40}\b(?:leadership|initiatives|programs?|teams?)\b|\bcross[ -]functional\b",
    "operating cadence": r"\boperating (?:rhythm|cadence|model)\b|\bbusiness review cadence\b",
    "process improvement": r"\bprocess (?:improvement|optimization|redesign|design)\b|\bcontinuous improvement\b|\broot cause analysis\b",
    "stakeholder alignment": r"\bstakeholder (?:alignment|engagement|management)\b|\binfluenc(?:e|ing) without (?:formal )?authority\b",
    "workflow automation": r"\b(?:workflow|process) automat(?:ion|e|ed|ing)\b|\bAI.enabled operations\b",
    "kpi dashboards": r"\bKPIs?\b|\b(?:performance|operations|executive) dashboards?\b|\bperformance tracking\b",
    "change management": r"\bchange management\b|\b(?:tool|process) (?:adoption|rollout)\b|\brollout and adoption\b",
    "governance": r"\bgovernance\b|\baccountability model\b|\bintake (?:process|system|management)\b",
    "program management": r"\bprogram management\b|\bprogram (?:delivery|execution|leadership)\b",
    "project management": r"\bproject management\b|\bproject (?:delivery|execution|planning)\b",
    "business operations": r"\bbusiness operations\b|\boperational excellence\b|\boperating model\b",
    "marketing operations": r"\bmarketing operations\b|\bmarketing automation\b|\bmarketing ops\b",
    "gtm programs": r"\bGTM\b|\bgo.to.market\b",
}
for key, pattern in GENERAL_OPERATIONS.items():
    GROUPS[key] = (key, pattern)


for n, roman in [(1, 'i'), (2, 'ii'), (3, 'iii')]:
    group = (f'phase {n}', rf'\bphase\s*(?:{n}|{roman})\b')
    GROUPS[f'phase {n}'] = GROUPS[f'phase {roman}'] = group


# Profiles may themselves use an alias; these still select the same category.
for canonical, aliases in {
    'budget': ['budgets', 'budgeting', 'financial management'],
    'vendor management': ['vendor oversight', 'cro management', 'cro oversight', 'managing cros', 'managing external vendors'],
    'line management': ['people leadership', 'personnel leadership', 'managing teams', 'leading teams'],
    'stakeholder management': ['stakeholder engagement'],
    'global trials': ['global clinical trials', 'global clinical studies', 'international clinical trials'],
    'vaccines': ['vaccine', 'vaccination'],
    'infectious disease': ['infectious diseases'],
}.items():
    for alias in aliases:
        GROUPS[alias] = GROUPS[canonical]


def skill_signals(text, configured):
    """Return category -> matched wording, retaining exact matching for unknown skills."""
    found = {}
    for term in configured:
        key = term.strip().lower()
        if key in GROUPS:
            category, pattern = GROUPS[key]
            match = re.search(pattern, text, re.I)
            if match:
                found.setdefault(category, match.group())
        elif has_term(text, term):
            found.setdefault(key, term)
    return found


def credential_review_text(text):
    """Remove city/state MD references, retaining degree mentions for review."""
    return re.sub(r'\b(?:Rockville|Baltimore|Bethesda|Gaithersburg|Frederick|Columbia|Silver Spring),\s*MD\b', '', text, flags=re.I)


def labeled_full_time_pay(text, employment_type):
    """Read a clearly labeled USD pay range, marking the unstated annual period."""
    if not re.search(r'full[ -]?time', str(employment_type), re.I):
        return ''
    amount = r'\$?\s*(\d{2,3}(?:,\d{3})+(?:\.\d+)?)'
    pattern = r'\bPay Range:\s*' + amount + r'\s*[-–—]\s*' + amount + r'\s*USD\b'
    for m in re.finditer(pattern, text, re.I):
        if re.search(r'hour|week|month|total|bonus|equity', text[max(0,m.start()-30):m.end()+35], re.I):
            continue
        low, high = (float(v.replace(',', '')) for v in m.groups())
        if 10000 <= low <= high:
            return f'USD {low:g}-{high:g} annual (period inferred from full-time pay range)'
    return ''
