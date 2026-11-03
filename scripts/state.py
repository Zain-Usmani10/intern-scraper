"""data/seen_jobs.json: jobs already found, alert queues, and failure counts."""

import config


def load_state():
    return config.read_json(
        config.STATE_FILE, default={"companies": {}, "last_heartbeat": None}
    )


def save_state(state):
    config.write_json(config.STATE_FILE, state)


def apply_results(state, results, now, settings):
    """Update state from scrape results. Return new jobs and status messages."""
    threshold = settings["alerts"]["failures_before_alert"]
    new_jobs = []
    messages = []

    for name, result in results.items():
        record = state["companies"].get(name)

        if "error" in result:
            print(f"[{name}] FAILED: {result['error']}")
            record = state["companies"].setdefault(name, {"failures": 0})
            record["failures"] = record.get("failures", 0) + 1
            if record["failures"] == threshold:
                messages.append(f"Scraper problem: {name}\n{result['error']}")
            continue

        jobs = result["jobs"]
        print(f"[{name}] {len(jobs)} matching jobs")

        if record is None or "seen" not in record:
            # First successful run: save what exists without alerting.
            failures = (record or {}).get("failures", 0)
            record = {"failures": failures, "seen": {url: now for url in jobs}}
            state["companies"][name] = record
            print(f"[{name}] Saved as baseline. No alerts sent.")
        else:
            new_jobs.extend(
                {"company": name, "title": job["title"], "location": job["location"], "url": url}
                for url, job in jobs.items()
                if url not in record["seen"]
            )

        if result.get("empty"):
            record["failures"] += 1
            if record["failures"] == threshold:
                messages.append(
                    f"No jobs found: {name}\n"
                    "This is normal if there are no openings. Otherwise, check the company."
                )
            continue

        if record["failures"] >= threshold:
            messages.append(f"Scraper recovered: {name}")
        record["failures"] = 0

    return new_jobs, messages
