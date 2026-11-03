"""Step 4: when detection fails, Claude investigates until a method passes.

Each attempt resets data/tmp/investigation.json with every earlier attempt
and the validator's reasons. Claude writes a proposal or a recommendation.
Python then validates the proposal itself. Claude never decides the result.
"""

import time

import config
from pipeline import claude, handoff, validate


def summary(report):
    return {key: report.get(key) for key in ("method", "params", "status", "reason", "counts")}


def investigate(name, careers_url, failed_reports, settings, log=print):
    """Return (report, recommendation). Both are None if Claude couldn't help."""
    limits = settings["claude"]
    deadline = time.time() + limits["max_minutes_per_company"] * 60
    attempts = [summary(report) for report in failed_reports]
    best_needs_approval = None

    for attempt in range(1, limits["max_attempts_per_company"] + 1):
        remaining = int(deadline - time.time())
        if remaining < 60:
            log("  Claude's time limit was reached.")
            break

        handoff.reset(
            "investigate_company", company=name, careers_url=careers_url,
            attempt=attempt, previous_attempts=attempts,
        )
        log(f"  Claude attempt {attempt}/{limits['max_attempts_per_company']}...")
        try:
            claude.run(
                "investigate_company",
                {"company": name, "attempt": attempt, "max_attempts": limits["max_attempts_per_company"],
                 "allowed_countries": " and ".join(settings["locations"]["allowed_countries"])},
                remaining, settings,
            )
        except TimeoutError:
            log("  Claude ran out of time.")
            break
        except claude.ClaudeUnavailable as error:
            log(f"  {error}")
            break
        except Exception as error:
            attempts.append({"error": str(error)[:300]})
            log(f"  Claude call failed: {str(error)[:150]}")
            continue

        result = handoff.read("investigate_company")
        if result.get("recommendation"):
            handoff.add_recommendation(name, careers_url, result["recommendation"])
            log("  Claude recommended a scraper change (saved to data/tmp/recommendations.json).")
            return best_needs_approval, result["recommendation"]

        proposal = result.get("proposal")
        if not isinstance(proposal, dict) or not proposal.get("method"):
            attempts.append({"error": "No proposal or recommendation was written.",
                             "notes": result.get("notes", "")})
            continue

        report = validate.validate(
            name, {"method": proposal["method"], "params": proposal.get("params") or {},
                   "source": "found by Claude"}, settings,
        )
        log(f"  Validator: {report['status']}: {report['reason']}")
        if report["status"] == "pass":
            return report, None
        if report["status"] == "needs_approval" and best_needs_approval is None:
            best_needs_approval = report
        attempts.append({**summary(report), "notes": result.get("notes", "")})

    return best_needs_approval, None
