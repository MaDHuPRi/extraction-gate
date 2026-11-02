"""Run the gate from a terminal or CI: python -m gate.cli v1 v2
Exit code 0 means Ship, and 1 means Block or No Decision, so a pipeline can stop on it."""
import sys

from .extractors import golden_docs, load_key, run_version
from .score import SHIP, compare


def main():
    if len(sys.argv) != 3:
        print("Usage: python -m gate.cli <baseline> <candidate>, for example v1 v2")
        return 2
    base, cand = sys.argv[1:]
    key = load_key()
    docs = golden_docs(key)
    result = compare(run_version(base, docs), run_version(cand, docs), key)
    print(f"{base} -> {cand}: {result.verdict}")
    print(f"Accuracy       {result.baseline_accuracy:.1%} -> {result.candidate_accuracy:.1%}")
    print(f"Dollars at risk ${result.baseline_risk:,.2f} -> ${result.candidate_risk:,.2f}")
    print(f"Fixed {len(result.fixed)}, broke {len(result.broke)}")
    for reason in result.reasons:
        print(f"- {reason}")
    return 0 if result.verdict == SHIP else 1


if __name__ == "__main__":
    sys.exit(main())
