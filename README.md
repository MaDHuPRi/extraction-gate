# Extraction Gate

Tests a W-2 extractor version before it ships. It runs the current and new versions on documents with known answers, counts what each mistake would cost in dollars, and returns **Ship**, **Block** or **No Decision**.

Live prototype: https://extraction-gate.streamlit.app

All data is synthetic. No paid service, account or API key is needed.

## Setup and run

Requires Python 3.10 or later.

```bash
pip install -r requirements.txt
streamlit run app.py        # opens the app
pytest -q                   # runs the 13 tests
python -m gate.cli v1 v2    # runs the gate in a terminal, exit code 1 means don't ship
```

To regenerate the test set: `python scripts/make_dataset.py`. It uses a fixed seed.

## How it works

1. `data/golden/` holds 32 synthetic W-2 PDFs in four layouts, with `answer_key.json`.
2. An extractor version reads each PDF. Versions live in `gate/extractors.py`.
3. `gate/score.py` marks each of 256 values (32 documents x 8 boxes) correct, wrong or missing.
4. A wrong value's risk is `abs(error) x field weight`. A blank value costs a flat $10 of review time, because a person will see it.
5. The gate blocks if any of these is true:
   - a critical value that was right is now silently wrong
   - dollars at risk rose by more than $25
   - a layout lost more than 2 points of accuracy
   - a reviewer-confirmed document fails

Incomplete or invalid predictions return No Decision, and never count as a pass.

The field weights in `gate/schema.py` are my assumptions, and can be edited in the app's sidebar. A tax reviewer should own them.

## Sample data and expected outputs

| Input | Result | Accuracy | Dollars at risk | Why |
|---|---|---|---|---|
| v1 to v2 | **BLOCK** | 83.6% to 98.0% | $420.00 to $17,440.25 | 5 Box 2 values now hold the Social Security tax amount |
| v1 to v3 | **SHIP** | 83.6% to 100.0% | $420.00 to $0.00 | 42 values fixed, none broken |
| Add the reviewer correction, then v1 to v3 | **BLOCK** | 82.6% to 98.5% | $19,924.15 to $19,504.15 | The pinned document fails on 4 fields |
| After the correction, v1 to v4 | **SHIP** | 82.6% to 100.0% | $19,924.15 to $0.00 | The pinned document passes |
| `samples/predictions_invalid.json` | **NO DECISION** | Not scored | Not scored | 29 documents missing, and one value isn't a number |

- **Valid upload example:** `samples/predictions_v3.json` shows the format the app accepts, as document name, then box, then amount. It should match v3's result.
- **Unreadable PDF:** the extractor returns blanks instead of guessing, which count as missing.

## Implemented, mocked, deferred

**Implemented:** dataset generator, four real extractor versions that read the PDFs, field scoring, the gate rules, per-layout and per-field results, reviewer correction, invalid input handling, CLI, tests.

**Mocked or synthetic:**
- All W-2s are synthetic.
- The Box 2 bug in v2 was seeded on purpose. The code really produces it.
- The production document in `data/production/` and its correction are synthetic.
- Corrections last for the app session. There's no database.

**Deferred:** other document types, scanned documents and OCR, saved run history, CI integration, and login.

**Optional and untested:** `scripts/run_groq.py` runs an LLM over the test set and saves predictions to upload. It needs a free Groq key, and it hasn't been run against the live API.

## Deploying

Push this folder to a public GitHub repo. On Streamlit Community Cloud, create an app with main file `app.py`. No secrets are needed.
