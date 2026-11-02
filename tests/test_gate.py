"""Scoring tests use tiny cases worked out by hand. End-to-end tests run the real PDFs."""
from gate.extractors import extract, golden_docs, load_key, run_version
from gate.schema import FIELDS, GateConfig
from gate.score import BLOCK, NO_DECISION, SHIP, compare, score, validate

TRUTH = dict(box1=50000, box2=6000, box3=50000, box4=3100, box5=50000, box6=725, box16=50000, box17=2000)
KEY = {"a.pdf": {"layout": "x", "fields": TRUTH}}


def preds(**changes):
    return {"a.pdf": {**TRUTH, **changes}}


def test_identical_versions_ship():
    assert compare(preds(), preds(), KEY).verdict == SHIP


def test_wrong_withholding_costs_the_full_error():
    # Box 2 reads 3,100 instead of 6,000: 2,900 x weight 1.0
    cell = next(c for c in score(preds(box2=3100), KEY, GateConfig()) if c.field == "box2")
    assert (cell.status, cell.risk) == ("wrong", 2900.0)


def test_wrong_wages_cost_the_marginal_rate():
    # Box 1 is off by 1,000: 1,000 x 0.22
    cell = next(c for c in score(preds(box1=49000), KEY, GateConfig()) if c.field == "box1")
    assert cell.risk == 220.0


def test_blank_value_costs_review_time_not_the_full_amount():
    cell = next(c for c in score(preds(box2=None), KEY, GateConfig()) if c.field == "box2")
    assert (cell.status, cell.risk) == ("missing", 10.0)


def test_blank_box_matching_a_zero_truth_is_correct():
    key = {"a.pdf": {"layout": "x", "fields": {**TRUTH, "box17": 0}}}
    cell = next(c for c in score(preds(box17=None), key, GateConfig()) if c.field == "box17")
    assert cell.status == "correct"


def test_silent_critical_error_blocks_even_when_accuracy_rises():
    key = {"a.pdf": KEY["a.pdf"], "b.pdf": KEY["a.pdf"]}
    base = {"a.pdf": dict(TRUTH), "b.pdf": {f: None for f in FIELDS}}
    cand = {"a.pdf": {**TRUTH, "box2": 3100}, "b.pdf": dict(TRUTH)}
    result = compare(base, cand, key)
    assert result.candidate_accuracy > result.baseline_accuracy
    assert result.verdict == BLOCK


def test_small_low_value_error_can_ship():
    # Box 16 off by $100 is $5 at risk, under the $25 limit. This is where weights differ
    # from a rule that blocks every regression.
    key = {"a.pdf": KEY["a.pdf"], **{f"{i}.pdf": KEY["a.pdf"] for i in range(40)}}
    base = {d: dict(TRUTH) for d in key}
    cand = {d: dict(TRUTH) for d in key}
    cand["a.pdf"]["box16"] = 50100
    assert compare(base, cand, key).verdict == SHIP


def test_pinned_document_must_pass():
    config = GateConfig(pinned_docs=["a.pdf"])
    assert compare(preds(box1=7812.4), preds(box1=7812.4), KEY, config).verdict == BLOCK


def test_incomplete_or_invalid_predictions_never_ship():
    assert compare(preds(), {}, KEY).verdict == NO_DECISION
    assert compare(preds(), preds(box2="six thousand"), KEY).verdict == NO_DECISION
    assert compare(preds(), {"a.pdf": {**TRUTH, "box99": 1}}, KEY).verdict == NO_DECISION
    assert validate([], KEY)


def test_unreadable_pdf_returns_blanks():
    assert extract(b"this is not a pdf", "v3") == {f: None for f in FIELDS}


def run(base, cand):
    key = load_key()
    docs = golden_docs(key)
    return compare(run_version(base, docs), run_version(cand, docs), key)


def test_v2_raises_accuracy_but_is_blocked():
    result = run("v1", "v2")
    assert result.candidate_accuracy > result.baseline_accuracy
    assert result.verdict == BLOCK
    assert {b.field for _, b in result.broke} == {"box2"}
    assert {b.layout for _, b in result.broke} == {"inline_fica_first"}


def test_v3_ships():
    assert run("v1", "v3").verdict == SHIP


def test_v4_reads_whole_dollar_amounts():
    from pathlib import Path
    data = Path("data/production/production_export_001.pdf").read_bytes()
    assert extract(data, "v3")["box1"] == 7812.40   # silently wrong
    assert extract(data, "v4")["box1"] == 62400.0
