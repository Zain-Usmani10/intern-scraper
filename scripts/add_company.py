"""Add companies from plain text, such as "Nvidia, Tesla, and Ericsson".

Usage:
    python scripts/add_company.py "Nvidia, Tesla, and Ericsson"

Steps for each company:
    1. Claude finds the name and careers URL      -> data/tmp/discovery.json
    2. Chromium inspects the careers page          -> data/tmp/evidence.json
    3. Detection picks method candidates, and the validator tests them
                                                   -> data/tmp/validation.json
    4. If none pass, Claude investigates           -> data/tmp/investigation.json
       and may recommend a scraper change          -> data/tmp/recommendations.json
    5. You confirm, then the company is saved      -> data/companies.json
       and the result is recorded                  -> data/companies_entered.json
"""

import argparse
import re
import sys
from datetime import date

import config
from pipeline import claude, detect, discover, handoff, investigate, probe, validate


NETWORK_ERRORS = re.compile(
    r"ERR_NAME_NOT_RESOLVED|ERR_INTERNET_DISCONNECTED|ERR_NETWORK_CHANGED|getaddrinfo failed",
    re.IGNORECASE,
)


class NetworkDown(Exception):
    pass


def check_network(error):
    if NETWORK_ERRORS.search(str(error)):
        raise NetworkDown("Your internet connection dropped. Nothing was saved. Try again later.")


def find_method(name, url, settings):
    """Return (report, recommendation) for one company."""
    print(f"\n=== {name}\n  {url}")
    try:
        evidence = probe.inspect(name, url, settings)
        print(f"  Page loaded (HTTP {evidence['status']}): {evidence['page_title'][:60]}")
    except Exception as error:
        check_network(error)
        print(f"  Couldn't load the page: {str(error).splitlines()[0][:150]}")
        evidence = {"company": name, "careers_url": url, "final_url": url, "error": str(error)[:300]}
        config.write_json(config.EVIDENCE_FILE, {**evidence, "candidates_tried": []})

    failed, waiting = [], None
    for candidate in detect.candidates(name, evidence, settings):
        report = validate.validate(name, candidate, settings)
        check_network(report["reason"])
        probe.record_tried(report)
        print(f"  {candidate['method']} ({candidate['source']}): {report['status']}. {report['reason']}")
        if report["status"] == "pass":
            return report, None
        if report["status"] == "needs_approval" and waiting is None:
            waiting = report
        else:
            failed.append(report)

    print("  Automatic detection didn't pass. Asking Claude to investigate.")
    report, recommendation = investigate.investigate(
        name, url, failed + ([waiting] if waiting else []), settings
    )
    return report or waiting, recommendation


def describe(report):
    counts = report["counts"]
    total = counts["reported_total"]
    total_text = f" of {total} reported" if total is not None else ""
    return (
        f"{report['method']}: read {counts['all_jobs']} jobs{total_text}, "
        f"{counts['internships']} internships, "
        f"{counts['internships_in_locations']} in your countries"
    )


def build_entry(name, report):
    return {
        "name": name,
        "method": report["method"],
        "params": report["params"],
        "verified": {
            "date": date.today().isoformat(),
            "status": report["status"],
            **report["counts"],
        },
    }


def record_entered(name, url, status, reason, method=None):
    entered = config.read_json(config.ENTERED_FILE, default=[])
    entered = [item for item in entered if item["name"].casefold() != name.casefold()]
    entered.append({
        "name": name, "careers_url": url, "entered": date.today().isoformat(),
        "status": status, "method": method, "reason": reason,
    })
    config.write_json(config.ENTERED_FILE, entered)


def confirm(question):
    return input(f"{question} Type y to confirm: ").strip().lower() == "y"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text", nargs="+", help="Company names, such as: Nvidia, Tesla, and Ericsson")
    parser.add_argument(
        "--yes", action="store_true",
        help="Don't ask. Add companies that pass. Record needs_approval ones for you to review.",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    settings = config.load_settings()
    handoff.prepare_tmp()
    config.write_json(config.CLAUDE_LOG_FILE, [])
    text = " ".join(args.text).strip()

    print("Finding companies and careers pages with Claude...")
    try:
        found = discover.discover(text, settings)
    except claude.ClaudeUnavailable as error:
        print(f"FAIL  {error}")
        return 1
    except Exception as error:
        print(f"FAIL  Company discovery failed: {str(error)[:200]}")
        return 1
    print(f"Found {len(found)}: {', '.join(company['name'] for company in found)}")

    companies = config.load_companies()
    results = []
    for company in found:
        name, url = company["name"], company["careers_url"]
        if any(existing["name"].casefold() == name.casefold() for existing in companies):
            results.append((name, url, "already added", None, None))
            continue
        if not url:
            results.append((name, url, "rejected", None, f"No careers URL found. {company['notes']}"))
            continue

        try:
            report, recommendation = find_method(name, url, settings)
        except NetworkDown as error:
            print(f"\nFAIL  {error}")
            return 1
        if report and any(
            detect.same_source(existing, report["method"], report["params"]) for existing in companies
        ):
            results.append((name, url, "already added", report, "Same source as an existing company."))
        elif report:
            results.append((name, url, report["status"], report, report["reason"]))
        elif recommendation:
            results.append((name, url, "needs new method", None, recommendation.get("summary", "")))
        else:
            results.append((name, url, "rejected", None, "No method passed validation."))

    print("\n" + "=" * 60 + "\nSUMMARY")
    added = 0
    for name, url, status, report, reason in results:
        print(f"\n{name}: {status.upper()}")
        if report:
            print(f"  {describe(report)}")
            for title in report["sample_titles"]:
                print(f"    {title}")
        if reason:
            print(f"  {reason}")

        if status in ("pass", "needs_approval"):
            if status == "needs_approval":
                print("  WARNING: Completeness can't be proven. Compare these with the site.")
                if args.yes:
                    print("  Not added. Run this company again without --yes to review it.")
                    record_entered(name, url, status, report["reason"], report["method"])
                    continue
            if args.yes or confirm(f"  Add {name}?"):
                companies.append(build_entry(name, report))
                config.write_json(config.COMPANIES_FILE, companies)
                record_entered(name, url, "added", report["reason"], report["method"])
                added += 1
            else:
                record_entered(name, url, "declined", report["reason"], report["method"])
        elif status != "already added":
            record_entered(name, url, status, reason)

    if added:
        print(f"\nAdded {added}. To send the changes to GitHub:")
        print("  git add data")
        print('  git commit -m "Add companies"')
        print("  git pull --rebase origin main")
        print("  git push")
    else:
        print("\nNo companies were added. data/companies.json was not changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
