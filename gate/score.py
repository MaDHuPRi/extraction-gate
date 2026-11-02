"""Score extractor output against the answer key, then decide Ship or Block.

This is plain code on purpose. The gate checks the AI, so it can't be AI itself.
"""
from dataclasses import dataclass, field

from .schema import FIELDS, GateConfig

SHIP, BLOCK, NO_DECISION = "SHIP", "BLOCK", "NO DECISION"
TOLERANCE = 0.005  # amounts must match to the cent


@dataclass
class Cell:
    doc: str
    layout: str
    field: str
    truth: float
    pred: object
    status: str   # correct, wrong or missing
    risk: float   # dollars at risk from this one value


@dataclass
class Decision:
    verdict: str
    reasons: list = field(default_factory=list)
    baseline_accuracy: float = 0.0
    candidate_accuracy: float = 0.0
    baseline_risk: float = 0.0
    candidate_risk: float = 0.0
    fixed: list = field(default_factory=list)
    broke: list = field(default_factory=list)
    layouts: dict = field(default_factory=dict)
    fields: dict = field(default_factory=dict)
    cells: list = field(default_factory=list)


def validate(preds, key):
    """Return reasons this prediction set can't be scored. Bad input must never become a Ship."""
    if not isinstance(preds, dict):
        return ["Predictions must be a JSON object keyed by document name."]
    problems = []
    missing = sorted(set(key) - set(preds))
    extra = sorted(set(preds) - set(key))
    if missing:
        problems.append(f"{len(missing)} test documents have no prediction, for example {missing[0]}.")
    if extra:
        problems.append(f"{len(extra)} predictions match no test document, for example {extra[0]}.")
    for doc, row in preds.items():
        if not isinstance(row, dict):
            problems.append(f"{doc}: the prediction isn't an object.")
            continue
        for name, value in row.items():
            if name not in FIELDS:
                problems.append(f"{doc}: unknown field '{name}'.")
            elif value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                problems.append(f"{doc}: {name} isn't a number ({value!r}).")
    return problems


def score(preds, key, config):
    """One Cell per document and field. A blank box in the key means zero."""
    cells = []
    for doc, entry in key.items():
        for name in FIELDS:
            truth = float(entry["fields"].get(name) or 0)
            pred = preds[doc].get(name)
            if pred is None:
                status = "correct" if truth == 0 else "missing"
                risk = 0.0 if truth == 0 else config.review_cost
            elif abs(float(pred) - truth) <= TOLERANCE:
                status, risk = "correct", 0.0
            else:
                status, risk = "wrong", abs(float(pred) - truth) * config.weights[name]
            cells.append(Cell(doc, entry["layout"], name, truth, pred, status, round(risk, 2)))
    return cells


def _accuracy(cells):
    return sum(c.status == "correct" for c in cells) / len(cells) if cells else 0.0


def _group(cells, attr):
    groups = {}
    for cell in cells:
        groups.setdefault(getattr(cell, attr), []).append(cell)
    return groups


def compare(baseline, candidate, key, config=None):
    """Run the gate. Rules are applied in a fixed order, and every failed rule is reported."""
    config = config or GateConfig()
    problems = validate(baseline, key) + validate(candidate, key)
    if problems:
        return Decision(NO_DECISION, reasons=problems[:6])

    old, new = score(baseline, key, config), score(candidate, key, config)
    pairs = list(zip(old, new))
    fixed = [(a, b) for a, b in pairs if a.status != "correct" and b.status == "correct"]
    broke = [(a, b) for a, b in pairs if a.status == "correct" and b.status != "correct"]
    decision = Decision(
        SHIP, baseline_accuracy=_accuracy(old), candidate_accuracy=_accuracy(new),
        baseline_risk=round(sum(c.risk for c in old), 2), candidate_risk=round(sum(c.risk for c in new), 2),
        fixed=fixed, broke=broke, cells=pairs)

    critical = config.critical_fields()
    silent = [(a, b) for a, b in broke if b.status == "wrong" and b.field in critical]
    if silent:
        decision.reasons.append(
            f"{len(silent)} critical values that were right are now silently wrong "
            f"(${sum(b.risk for _, b in silent):,.2f} at risk).")

    added = decision.candidate_risk - decision.baseline_risk
    if added > config.max_added_risk:
        decision.reasons.append(f"Dollars at risk rose by ${added:,.2f}, over the ${config.max_added_risk:,.2f} limit.")

    old_layouts, new_layouts = _group(old, "layout"), _group(new, "layout")
    for layout in sorted(old_layouts):
        before, after = _accuracy(old_layouts[layout]), _accuracy(new_layouts[layout])
        decision.layouts[layout] = (before, after)
        if before - after > config.max_layout_drop:
            decision.reasons.append(f"Layout '{layout}' fell from {before:.1%} to {after:.1%}.")

    old_fields, new_fields = _group(old, "field"), _group(new, "field")
    for name in FIELDS:
        decision.fields[name] = (_accuracy(old_fields[name]), _accuracy(new_fields[name]))

    for doc in config.pinned_docs:
        failed = [c for c in new if c.doc == doc and c.status != "correct"]
        if failed:
            decision.reasons.append(f"Reviewer-confirmed document {doc} fails on {len(failed)} fields.")

    if decision.reasons:
        decision.verdict = BLOCK
    else:
        decision.reasons.append("No critical regressions, no added risk, no layout got worse, and all pinned documents pass.")
    return decision
