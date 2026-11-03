"""Step 3: prove a method reads every job, with no AI.

Statuses:
    pass            Proven complete and stable.
    needs_approval  Works, but completeness can't be proven. You decide.
    fail            Doesn't work. The reason says why.

Every report is also saved to data/tmp/validation.json.
"""

import time

import config
import filters
import methods


def check(report, name, ok, detail):
    report["checks"].append({"check": name, "ok": ok, "detail": detail})
    return ok


def finish(report, status, reason):
    report["status"] = status
    report["reason"] = reason
    config.write_json(config.VALIDATION_FILE, report)
    return report


def validate(company_name, candidate, settings):
    method, params = candidate["method"], candidate.get("params") or {}
    source = candidate.get("source", "")
    report = {
        "company": company_name, "method": method, "params": params, "source": source,
        "status": None, "reason": "", "checks": [], "counts": {}, "sample_titles": [],
    }

    catalog = config.load_methods()
    if not check(report, "method exists", method in catalog, method):
        return finish(report, "fail", f"Unknown method: {method}")
    missing = [
        key for key, spec in catalog[method]["params"].items()
        if spec["required"] and not params.get(key)
    ]
    if not check(report, "required params", not missing, ", ".join(missing) or "all present"):
        return finish(report, "fail", f"Missing params: {', '.join(missing)}")

    runs = []
    for attempt in range(2):
        if attempt:
            time.sleep(settings["add_company"]["seconds_between_validation_scrapes"])
        try:
            runs.append(methods.fetch(method, params, settings))
        except Exception as error:
            detail = f"{type(error).__name__}: {str(error).splitlines()[0][:200]}"
            check(report, f"scrape {attempt + 1}", False, detail)
            return finish(report, "fail", f"The method failed: {detail}")
        check(report, f"scrape {attempt + 1}", True, f"{len(runs[-1]['jobs'])} jobs")

    first, second = runs
    all_jobs = first["jobs"]
    if not check(report, "found jobs", bool(all_jobs), f"{len(all_jobs)} jobs"):
        return finish(report, "fail", "The method read 0 jobs, so it can't be verified.")

    difference = len(set(first["jobs"]) ^ set(second["jobs"]))
    allowed = max(2, len(all_jobs) * settings["add_company"]["stability_tolerance_percent"] // 100)
    if not check(report, "stable results", difference <= allowed,
                 f"{difference} jobs differed between two scrapes (allowed {allowed})"):
        return finish(report, "fail", "Two scrapes returned different jobs, so job links aren't stable.")

    untitled = sum(job["title"] == "New posting" for job in all_jobs.values())
    if not check(report, "readable titles", untitled <= len(all_jobs) * 0.2,
                 f"{untitled} of {len(all_jobs)} jobs have no title"):
        return finish(
            report, "fail",
            f"{untitled} of {len(all_jobs)} jobs have no readable title, so alerts would be useless.",
        )

    company = {"filters": {}}
    kept = filters.apply_filters(all_jobs, company, settings)
    internships = [url for url, job in all_jobs.items()
                   if filters.is_internship(job["title"], url, settings)]
    report["counts"] = {
        "all_jobs": len(all_jobs),
        "reported_total": first["reported_total"],
        "internships": len(internships),
        "internships_in_locations": len(kept),
    }
    shown = settings["add_company"]["max_titles_shown"]
    report["sample_titles"] = sorted(
        f"{job['title']} ({job['location']})" if job["location"] else job["title"]
        for job in kept.values()
    )[:shown]

    completeness = catalog[method]["completeness"]
    reported = first["reported_total"]
    if completeness == "api_total" or (completeness == "page_total_or_approval" and reported is not None):
        matches = reported is not None and len(all_jobs) == reported
        if not check(report, "count matches site total", matches,
                     f"read {len(all_jobs)} of {reported} reported"):
            return finish(report, "fail", f"Read {len(all_jobs)} of the {reported} jobs the site reports.")
    elif completeness == "complete_list":
        check(report, "complete list", True, "API returns the whole board in one response")
    else:
        check(report, "count matches site total", False, "this site reports no total")
        return finish(
            report, "needs_approval",
            "The site reports no total, so compare these results with the site before approving.",
        )

    if source == "guessed from the company name":
        return finish(
            report, "needs_approval",
            f"The board name was guessed. Confirm these jobs belong to {company_name}.",
        )
    return finish(report, "pass", "Read every job the site reports, twice, with stable results.")
