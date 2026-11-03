"""data/seen_jobs.json: the currently active jobs, alert queues, and failure counts.

Each company's "seen" holds the matching jobs still on its site:
    {url: {"title", "location", "first_seen", "last_seen"}}

Every run reads each company's full listing, so checking which stored jobs
are still active needs no extra requests. A job missing from more than
settings.alerts.forget_after_missed_runs successful runs in a row is removed.
Waiting a few runs stops a job that briefly disappears from being alerted
again when it comes back.
"""

import config


def load_state():
    return config.read_json(
        config.STATE_FILE, default={"companies": {}, "last_heartbeat": None}
    )


def save_state(state):
    config.write_json(config.STATE_FILE, state)


def update_seen(record, jobs, today, forget_after_missed_runs):
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
                     "first_seen": first_seen, "last_seen": today, "missed_runs": 0}

    for url in [url for url in seen if url not in jobs]:
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
            update_seen(record, jobs, today, forget_after)
            print(f"[{name}] Saved as baseline. No alerts sent.")
        else:
            new = update_seen(record, jobs, today, forget_after)
            new_jobs.extend(
                {"company": name, "title": job["title"], "location": job["location"], "url": url}
                for url, job in new.items()
            )

        if record.get("failures", 0) >= threshold:
            messages.append(f"Scraper recovered: {name}")
        record["failures"] = 0

    return new_jobs, messages
