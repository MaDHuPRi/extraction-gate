"""The W-2 extractor versions under test.

Each version is real code that reads the PDFs. They differ only in their label rules, the same
way two prompt versions would differ. The gate doesn't care how a version works: it only sees
the predictions, so an LLM's output can be tested the same way (scripts/run_groq.py).

v1  baseline, standard W-2 labels only
v2  adds payroll-export labels, with one broad pattern that causes a seeded Box 2 bug
v3  fixes that pattern
v4  also reads whole-dollar amounts, after a reviewer reports a miss on a real-looking export
"""
import io
import json
import re
from pathlib import Path

import pdfplumber

from .schema import FIELDS

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "data" / "golden"

MONEY_CENTS = r"\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2}"
MONEY_WHOLE = MONEY_CENTS + r"|\d{1,3}(?:,\d{3})+"

V1 = {
    "box1": r"wages,?\s+tips,?\s+other\s+comp\S*",
    "box2": r"federal\s+income\s+tax\s+withheld",
    "box3": r"social\s+security\s+wages",
    "box4": r"social\s+security\s+tax\s+withheld",
    "box5": r"medicare\s+wages(?:\s+and\s+tips)?",
    "box6": r"medicare\s+tax\s+withheld",
    "box16": r"state\s+wages(?:,?\s+tips,?\s+etc\.?)?",
    "box17": r"state\s+income\s+tax",
}
V2 = dict(V1)
V2.update({
    "box1": V1["box1"] + r"|gross\s+taxable\s+wages",
    "box2": V1["box2"] + r"|federal\s+w/h|tax\s+withheld",   # too broad: also matches Social Security lines
    "box3": V1["box3"] + r"|oasdi\s+wages",
    "box4": V1["box4"] + r"|oasdi\s+tax",
    "box6": V1["box6"] + r"|medicare\s+tax",
    "box17": V1["box17"] + r"|state\s+tax",
})
V3 = dict(V2)
V3["box2"] = V1["box2"] + r"|federal\s+w/h"

VERSIONS = {
    "v1": {"labels": V1, "money": MONEY_CENTS},
    "v2": {"labels": V2, "money": MONEY_CENTS},
    "v3": {"labels": V3, "money": MONEY_CENTS},
    "v4": {"labels": V3, "money": MONEY_WHOLE},
}


def _to_float(text):
    return float(text.replace(",", ""))


def _inline(text, pattern, money):
    """Label and amount on one line: take the first amount after the label."""
    for line in text.splitlines():
        match = re.search(pattern, line, re.I)
        if match:
            amount = re.search(money, line[match.end():])
            if amount:
                return _to_float(amount.group(0))
    return None


def _under_label(words, pattern, money):
    """Boxed layout: take the amount printed under the label, in the same column."""
    for start in range(len(words)):
        run = []
        for word in words[start:start + 8]:
            if run and abs(word["top"] - run[0]["top"]) > 2:
                break
            run.append(word)
            if re.fullmatch(pattern, " ".join(w["text"] for w in run), re.I):
                bottom, left = run[0]["bottom"], run[0]["x0"]
                below = [w for w in words if 0 <= w["top"] - bottom < 26 and abs(w["x0"] - left) < 90
                         and re.fullmatch(money, w["text"])]
                if below:
                    return _to_float(min(below, key=lambda w: w["top"])["text"])
    return None


def extract(pdf_bytes, version):
    """Read one PDF. An unreadable file returns blanks, so it counts as missing and never as a guess."""
    rules = VERSIONS[version]
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[0]
            text, words = page.extract_text() or "", page.extract_words()
    except Exception:
        return {name: None for name in FIELDS}
    row = {}
    for name in FIELDS:
        pattern = rules["labels"][name]
        value = _inline(text, pattern, rules["money"])
        row[name] = value if value is not None else _under_label(words, pattern, rules["money"])
    return row


def load_key(folder=GOLDEN):
    return json.loads((Path(folder) / "answer_key.json").read_text())


def run_version(version, docs):
    """Run a version over {doc name: path}. Returns {doc name: {field: value}}."""
    return {doc: extract(Path(path).read_bytes(), version) for doc, path in docs.items()}


def golden_docs(key=None):
    key = key or load_key()
    return {doc: GOLDEN / doc for doc in key}
