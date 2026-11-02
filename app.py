"""Extraction Gate: test a W-2 extractor version before it ships."""
import json
from pathlib import Path

import pandas as pd
import pdfplumber
import streamlit as st

from gate.extractors import VERSIONS, extract, golden_docs, load_key, run_version
from gate.schema import FIELD_NAMES, FIELDS, GateConfig
from gate.score import BLOCK, NO_DECISION, SHIP, compare

ROOT = Path(__file__).parent
PROD_DIR = ROOT / "data" / "production"
PROD_DOC = "production_export_001.pdf"
COLORS = {SHIP: "#1f4e3d", BLOCK: "#8c2f1b", NO_DECISION: "#6b5b1e"}

st.set_page_config(page_title="Extraction Gate", layout="wide")
st.markdown("""<style>
.block-container {max-width: 1080px; padding-top: 2.2rem;}
.verdict {padding: 1.1rem 1.3rem; border-radius: 6px; color: #fff; margin: .4rem 0 1rem;}
.verdict b {font-size: 1.7rem; letter-spacing: .02em;}
.verdict ul {margin: .5rem 0 0; padding-left: 1.1rem;}
.small {color: #5f5c55; font-size: .9rem;}
</style>""", unsafe_allow_html=True)

st.session_state.setdefault("corrected", False)
key = load_key()
docs = golden_docs(key)
config = GateConfig()
if st.session_state.corrected:
    correction = json.loads((PROD_DIR / "reviewer_correction.json").read_text())
    key.update(correction)
    docs[PROD_DOC] = PROD_DIR / PROD_DOC
    config.pinned_docs = [PROD_DOC]

st.title("Extraction Gate")
st.markdown("Should this extractor version ship? It tests a change on documents with known answers "
            "and counts what a mistake would cost, not just how many fields match.")
st.caption("All W-2s are synthetic. The Box 2 bug in v2 was seeded on purpose. Field weights are my "
           "assumptions, for a tax reviewer to set.")

with st.sidebar:
    st.header("Compare")
    names = list(VERSIONS)
    baseline = st.selectbox("Live version", names, index=0)
    source = st.radio("Candidate", ["Extractor version", "Upload predictions JSON"])
    candidate_name, candidate_preds, upload_error = st.selectbox("Candidate version", names, index=1) \
        if source == "Extractor version" else "uploaded", None, None
    if source != "Extractor version":
        upload = st.file_uploader("Predictions JSON", type="json")
        use_bad = st.button("Try the invalid sample")
        raw = upload.getvalue() if upload else None
        if use_bad:
            raw = (ROOT / "samples" / "predictions_invalid.json").read_bytes()
        if raw:
            try:
                candidate_preds = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                upload_error = "That file isn't valid JSON."

    st.header("Field weights")
    st.caption("Dollars of tax effect per $1 of error.")
    for name in FIELDS:
        config.weights[name] = st.number_input(FIELD_NAMES[name], 0.0, 1.0, config.weights[name],
                                               0.01, format="%.4f")
    config.max_added_risk = st.number_input("Allowed added risk ($)", 0.0, value=config.max_added_risk)


@st.cache_data
def predictions(version, doc_names, include_prod):
    paths = {d: (PROD_DIR / d if d == PROD_DOC else ROOT / "data" / "golden" / d) for d in doc_names}
    return run_version(version, paths)


def printed_line(doc, value):
    """The line in the PDF that holds this value, so a reviewer can see the source."""
    if value is None:
        return ""
    folder = PROD_DIR if doc == PROD_DOC else ROOT / "data" / "golden"
    with pdfplumber.open(folder / doc) as pdf:
        text = pdf.pages[0].extract_text() or ""
    for line in text.splitlines():
        if f"{value:,.2f}" in line:
            return line
    return ""


doc_names = tuple(docs)
base_preds = predictions(baseline, doc_names, st.session_state.corrected)
if source == "Extractor version":
    candidate_preds = predictions(candidate_name, doc_names, st.session_state.corrected)

if source != "Extractor version" and candidate_preds is None and not upload_error:
    st.info("Upload a predictions JSON, or try the invalid sample, to run the gate.")
    st.stop()

if upload_error:
    result = None
    verdict, reasons = NO_DECISION, [upload_error]
else:
    result = compare(base_preds, candidate_preds, key, config)
    verdict, reasons = result.verdict, result.reasons

items = "".join(f"<li>{r}</li>" for r in reasons)
st.markdown(f"<div class='verdict' style='background:{COLORS[verdict]}'><b>{verdict}</b>"
            f"<div>{baseline} to {candidate_name}</div><ul>{items}</ul></div>", unsafe_allow_html=True)
if verdict == NO_DECISION:
    st.markdown("The gate won't score this input. A run it can't verify never counts as a pass.")
    st.stop()

a, b, c, d = st.columns(4)
a.metric("Field accuracy", f"{result.candidate_accuracy:.1%}",
         f"{(result.candidate_accuracy - result.baseline_accuracy) * 100:+.1f} pts")
b.metric("Dollars at risk", f"${result.candidate_risk:,.2f}",
         f"{result.candidate_risk - result.baseline_risk:+,.2f}", delta_color="inverse")
c.metric("Values fixed", len(result.fixed))
d.metric("Values broken", len(result.broke))
if result.candidate_accuracy > result.baseline_accuracy and verdict == BLOCK:
    st.warning("Accuracy went up and this version still shouldn't ship. An accuracy check alone would have passed it.")

broke_tab, fixed_tab, layout_tab, field_tab = st.tabs(["What broke", "What got fixed", "By layout", "By field"])
with broke_tab:
    if result.broke:
        rows = [{"Document": b_.doc, "Field": FIELD_NAMES[b_.field], "Correct": b_.truth,
                 f"{candidate_name} read": b_.pred, "At risk ($)": b_.risk,
                 "Printed on the document": printed_line(b_.doc, b_.pred)} for _, b_ in result.broke]
        st.dataframe(pd.DataFrame(rows).sort_values("At risk ($)", ascending=False), hide_index=True, width="stretch")
    else:
        st.write("Nothing that was right got worse.")
with fixed_tab:
    if result.fixed:
        counts = pd.Series([FIELD_NAMES[b_.field] for _, b_ in result.fixed]).value_counts()
        st.dataframe(counts.rename("Values fixed"), width="stretch")
    else:
        st.write("No values changed from wrong to right.")
with layout_tab:
    st.dataframe(pd.DataFrame([{"Layout": k, "Live": f"{v[0]:.1%}", "Candidate": f"{v[1]:.1%}"}
                               for k, v in result.layouts.items()]), hide_index=True, width="stretch")
with field_tab:
    st.dataframe(pd.DataFrame([{"Field": FIELD_NAMES[k], "Weight": config.weights[k], "Live": f"{v[0]:.1%}",
                                "Candidate": f"{v[1]:.1%}"} for k, v in result.fields.items()]),
                 hide_index=True, width="stretch")

st.divider()
st.subheader("Reviewer correction")
st.markdown("A reviewer finds an error on a document outside the test set. Their correction becomes a "
            "pinned test case, so no later version can ship while it still gets that document wrong.")
correction = json.loads((PROD_DIR / "reviewer_correction.json").read_text())[PROD_DOC]["fields"]
seen = extract((PROD_DIR / PROD_DOC).read_bytes(), "v3")
st.dataframe(pd.DataFrame([{"Field": FIELD_NAMES[f], "v3 read": seen[f], "Reviewer says": correction[f],
                            "Match": "yes" if seen[f] == correction[f] else "NO"} for f in FIELDS]),
             hide_index=True, width="stretch")
left, right = st.columns(2)
if left.button("Add correction to the test set", disabled=st.session_state.corrected, type="primary"):
    st.session_state.corrected = True
    st.rerun()
if right.button("Reset demo", disabled=not st.session_state.corrected):
    st.session_state.corrected = False
    st.rerun()
if st.session_state.corrected:
    st.success(f"Pinned {PROD_DOC}. The test set now has {len(key)} documents. Compare v1 to v3, then v1 to v4.")
