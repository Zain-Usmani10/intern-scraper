"""data/seen_jobs.json: the currently active jobs, alert queues, and failure counts.

Each company's "seen" holds the matching jobs still on its site:
    {url: {"title", "location", "first_seen", "last_seen"}}

Every run reads each company's full listing, so checking which stored jobs
are still active needs no extra requests. A job missing from more than
settings.alerts.forget_after_missed_runs successful runs in a row is removed.
Waiting a few runs stops a job that briefly disappears from being alerted
again when it comes back.

A posting the site sent broken (no title or link) is still listed, so it isn't
counted as missed: the saved job whose link holds its ID is kept. If its ID
matches no saved job, or it has none, no job is counted as missed that run.
"""

import config
from methods.common import id_in_url


def load_state():
    return config.read_json(
        config.STATE_FILE, default={"companies": {}, "last_heartbeat": None}
    )


def save_state(state):
    config.write_json(config.STATE_FILE, state)


def update_seen(record, jobs, today, forget_after_missed_runs, broken=()):
    """Refresh the active jobs. Return the jobs that weren't stored before."""
    seen = record.setdefault("seen", {})
    new = {}
    for url, job in jobs.items():
        old = seen.get(url)
        if old is None:
            new[url] = job
        # Older files stored only a timestamp string.
        first_seen = old["first_seen"] if isinstance(old, dict) else (old or today)[:10]
        seen[url] = {"title": job["title"], "location": job["location"],
                     "country": job.get("country", ""),
                     "first_seen": first_seen, "last_seen": today, "missed_runs": 0}

    missing = [url for url in seen if url not in jobs]
    unsure = any(
        posting_id is None or not any(id_in_url(posting_id, url) for url in missing)
        for posting_id in broken
    )
    for url in missing:
        if unsure or any(posting_id and id_in_url(posting_id, url) for posting_id in broken):
            continue  # Still listed, just broken this run: not a miss.
        item = seen[url]
        if not isinstance(item, dict):
            item = seen[url] = {"title": "", "location": "", "first_seen": item[:10],
                                "last_seen": item[:10], "missed_runs": 0}
        item["missed_runs"] = item.get("missed_runs", 0) + 1
        if item["missed_runs"] > forget_after_missed_runs:
            del seen[url]
    return new


def apply_results(state, results, today, settings):
    """Update state from scrape results. Return new jobs and status messages.

    "today" is the local date, like "2026-11-03".
    """
    threshold = settings["alerts"]["failures_before_alert"]
    forget_after = settings["alerts"]["forget_after_missed_runs"]
    new_jobs = []
    messages = []

    # Companies removed from companies.json are forgotten.
    for name in [name for name in state["companies"] if name not in results]:
        del state["companies"][name]

    for name, result in results.items():
        record = state["companies"].get(name)

        if "error" in result:
            # A failed scrape says nothing about which jobs are still active.
            print(f"[{name}] FAILED: {result['error']}")
            record = state["companies"].setdefault(name, {"failures": 0})
            record["failures"] = record.get("failures", 0) + 1
            if record["failures"] == threshold:
                messages.append(f"Scraper problem: {name}\n{result['error']}")
            continue

        jobs = result["jobs"]
        broken = result.get("broken") or []
        print(f"[{name}] {len(jobs)} matching jobs")

        if result.get("empty"):
            # The site returned nothing at all, which is more likely a broken
            # page than every job closing at once. Keep the stored jobs.
            record = state["companies"].setdefault(name, {"failures": 0})
            record.setdefault("seen", {})  # So its first job is alerted, not taken as a baseline.
            record["failures"] = record.get("failures", 0) + 1
            if record["failures"] == threshold:
                messages.append(
                    f"No jobs found: {name}\n"
                    "This is normal if there are no openings. Otherwise, check the company."
                )
            continue

        if record is None or "seen" not in record:
            # First successful run: save what exists without alerting.
            record = state["companies"].setdefault(name, {"failures": 0})
            update_seen(record, jobs, today, forget_after, broken)
            print(f"[{name}] Saved as baseline. No alerts sent.")
        else:
            new = update_seen(record, jobs, today, forget_after, broken)
            new_jobs.extend(
                {"company": name, "title": job["title"], "location": job["location"],
                 "country": job.get("country", ""), "url": url}
                for url, job in new.items()
            )

        if record.get("failures", 0) >= threshold:
            messages.append(f"Scraper recovered: {name}")
        record["failures"] = 0

        # Broken postings are skipped quietly, unless they last several runs.
        if broken:
            print(f"[{name}] {len(broken)} broken posting(s) skipped: {', '.join(i or 'no ID' for i in broken)}")
            record["broken_runs"] = record.get("broken_runs", 0) + 1
            if record["broken_runs"] == threshold:
                messages.append(
                    f"Broken postings: {name}\n"
                    f"{len(broken)} posting(s) came back without a title or link for "
                    f"{threshold} runs in a row (ID: {', '.join(i or 'none' for i in broken)}). "
                    "Your saved jobs there are kept until this clears."
                )
        else:
            record.pop("broken_runs", None)

    return new_jobs, messages
