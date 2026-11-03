"""Test one method and its params with the real validator.

Usage:
    python scripts/test_method.py --investigation
        Tests "proposal" from data/tmp/investigation.json. Claude uses this.
    python scripts/test_method.py greenhouse '{"board": "figureai"}' --company Figure
        Tests any method by hand.

The report prints and is saved to data/tmp/validation.json.
"""

import argparse
import json
import sys

import config
from pipeline import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("method", nargs="?")
    parser.add_argument("params", nargs="?", default="{}")
    parser.add_argument("--company", default="")
    parser.add_argument("--investigation", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    if args.investigation:
        investigation = config.read_json(config.TMP / "investigation.json")
        proposal = investigation.get("proposal") or {}
        method, params = proposal.get("method"), proposal.get("params") or {}
        company = investigation.get("company", "")
        source = "found by Claude"
    else:
        method, params, company, source = args.method, json.loads(args.params), args.company, "manual test"

    if not method:
        print("No method given. Put a proposal in data/tmp/investigation.json or pass a method.")
        return 1

    report = validate.validate(
        company, {"method": method, "params": params, "source": source}, config.load_settings()
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] in ("pass", "needs_approval") else 1


if __name__ == "__main__":
    sys.exit(main())
