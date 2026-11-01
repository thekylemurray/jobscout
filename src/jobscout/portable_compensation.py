"""Conservative Washington-aware compensation assessment for portable profiles.

Global salary envelopes can contain an inapplicable high-cost city band. Reject
only when the explicit applicable Washington/other-US maxima are all below the
candidate's floor. An unknown geography or pay basis remains a review note.
"""
from __future__ import annotations
import re

AMOUNT = r'(?:US\$|\$)\s*(\d{2,3}(?:,\d{3})+(?:\.\d+)?|\d{5,6}(?:\.\d+)?|\d{2,3}(?:\.\d+)?[kK])'
RANGE = re.compile(AMOUNT + r'\s*(?:-|–|—|to)\s*' + AMOUNT + r'(?:\s*USD\b)?', re.I)
REGION = re.compile(
    r'\b(?P<seattle>Seattle(?:\s+(?:metro|metropolitan\s+area))?|Washington(?:\s+State)?|\bWA\b)'
    r'|(?P<other>other\s+(?:U\.?S\.?|United States|US|domestic)\s+(?:locations?|areas?|regions?|markets?)|'
    r'(?:rest|remainder)\s+of\s+(?:the\s+)?(?:U\.?S\.?|United States|US))'
    r'|(?P<excluded>San Francisco|Bay Area|California|New York(?: City)?|'
    r'Boston|Los Angeles|Massachusetts|Colorado|Boulder|Canada)',
    re.I
)
OTE = re.compile(r'\b(?:on[- ]target earnings|OTE)\b', re.I)
BASE = re.compile(r'\b(?:base salary|base pay|annual salary|salary range|compensation ranges?)\b', re.I)


def _number(value):
    n = float(value.rstrip("kK").replace(",", ""))
    return n * 1000 if value.lower().endswith("k") else n


def _ranges(text: str):
    found = []
    for m in RANGE.finditer(text):
        low, high = _number(m.group(1)), _number(m.group(2))
        if not 30000 <= low <= high <= 1000000:
            continue
        prefix = text[max(0, m.start()-170):m.start()]
        regions = list(REGION.finditer(prefix))
        nearest = regions[-1] if regions else None
        group = nearest.lastgroup if nearest else None
        # A region label must be close enough to the dollar amounts to
        # distinguish it from general text elsewhere in the posting.
        if nearest and len(prefix) - nearest.end() > 75:
            group = None
        context = text[max(0, m.start()-180):m.end()+40]
        # Don't interpret bonus/equity as annual base.
        if re.search(r'\b(?:bonus|equity|stock)\s+(?:range|opportunity|compensation)\b',
                     prefix[-70:], re.I):
            continue
        found.append((group, low, high, context, m.start()))
    return found


def location_compensation_review(description: str, floor: float, state: str) -> tuple[str, list[str]]:
    """Return (confirmed violation or '', review messages).

    Never infer that the candidate lives in Seattle just from Washington State.
    """
    text = re.sub(r'\s+', ' ', description or '')
    notes = []
    ranges = _ranges(text)
    if not ranges:
        return '', notes

    if state.strip().lower() not in {'washington', 'wa'}:
        return '', notes

    # On-target earnings includes base and variable pay. If a clearly identified
    # national OTE ceiling is below the required *base* floor, base cannot reach
    # that floor. Never report OTE as though it were base pay.
    for group, low, high, context, pos in ranges:
        ote_context = text[max(0, pos-115):pos]
        if OTE.search(ote_context) and group in {None, 'seattle', 'other'}:
            if high < floor and len(ranges) == 1 and not re.search(r'\b(?:CAD|Canada)\b', context, re.I):
                return f'USD on-target earnings ceiling {high:g} below required base {floor:g}', notes
            notes.append("on-target earnings disclosed; base salary is not independently established")
            break

    bands = [r for r in ranges if r[0] in {'seattle', 'other'}]
    unknown = [r for r in ranges if r[0] is None]
    # Require two explicit regional bands (at least one Washington/other-US)
    # before interpreting geography; a lone tier may not describe all of WA.
    if len(ranges) >= 2 and bands:
        notes.append('geographic salary bands: Washington location and applicable base must be confirmed')
        all_below = all(high < floor for _group, _lo, high, _ctx, _pos in bands)
        if all_below and not unknown and BASE.search(text[max(0,ranges[0][4]-250):ranges[0][4]]):
            ceiling = max(r[2] for r in bands)
            return (f'Washington-compatible salary bands max at USD {ceiling:g}, '
                    f'below required base {floor:g}'), notes
    return '', notes
