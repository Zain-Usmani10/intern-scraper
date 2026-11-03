"""Main scraper: reads data/companies.json and runs each company's method.

Usage:
    python scripts/scraper.py                Run normally.
    python scripts/scraper.py --dry-run      Show what was found. Sends nothing, saves nothing.
    python scripts/scraper.py --test-alert   Send a test message to each alert channel.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import alerts
import config
import filters
import methods
import state as state_store


def scrape_company(company, settings):
    """Run the company's method, then filter.

    Returns {"jobs": {url: {title, location}}, "empty": bool} or {"error": str}.
    "empty" means the method read no jobs at all, before filtering.
    """
    try:
        result = methods.fetch(company["method"], company["params"], settings)
    except Exception as error:
        return {"error": f"{type(error).__name__}: {str(error).splitlines()[0][:200]}"}

    # A partial read would miss new jobs and wrongly mark unread ones as gone,
    # so it counts as a failed run. Jobs posted mid-read get a small margin.
    reported, read = result["reported_total"], len(result["jobs"])
    margin = max(2, (reported or 0) * settings["add_company"]["stability_tolerance_percent"] // 100)
    if reported is not None and read < reported - margin:
        return {"error": f"Read only {read} of the {reported} jobs the site reports"}

    jobs = filters.apply_filters(result["jobs"], company, settings)
    return {"jobs": jobs, "empty": not result["jobs"]}


def scrape_all(companies, settings):
    workers = settings["scraping"]["companies_at_once"]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda company: scrape_company(company, settings), companies)
        return {company["name"]: result for company, result in zip(companies, results)}


def print_dry_run(results):
    for name, result in results.items():
        if "error" in result:
            print(f"\n{name}: FAILED: {result['error']}")
            continue
        print(f"\n{name}: {len(result['jobs'])} matching jobs")
        for url, job in result["jobs"].items():
            location = f" ({job['location']})" if job["location"] else ""
            print(f"  {job['title']}{location}\n    {url}")


def send_test_alerts(settings):
    jobs = alerts.SAMPLE_JOBS
    telegram = alerts.send_telegram("TEST (dummy data)\n\n" + alerts.format_job(jobs[2]))
    slot = alerts.latest_email_slot(
        datetime.now(ZoneInfo(settings["alerts"]["timezone"])), settings
    )
    subject, text, body = alerts.build_email(jobs, slot)
    gmail = alerts.send_gmail(f"TEST (dummy data): {subject}", text, body, include_friend=False)
    print(f"Telegram: {'sent' if telegram else 'NOT sent'}")
    print(f"Gmail: {'sent' if gmail else 'NOT sent'}")
    return 0 if telegram or gmail else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-alert", action="store_true")
    args = parser.parse_args()

    load_dotenv(config.ROOT / ".env")
    sys.stdout.reconfigure(errors="replace")
    settings = config.load_settings()

    if args.test_alert:
        return send_test_alerts(settings)

    if not args.dry_run and not (alerts.telegram_ready() or alerts.gmail_ready()):
        print("No alert channel is configured. Add your settings to .env.")
        return 1

    companies = config.load_companies()
    results = scrape_all(companies, settings)

    if args.dry_run:
        print_dry_run(results)
        return 0

    today = datetime.now(ZoneInfo(settings["alerts"]["timezone"])).date().isoformat()
    state = state_store.load_state()
    new_jobs, messages = state_store.apply_results(state, results, today, settings)

    # New jobs wait in these saved queues until each one is delivered.
    state["telegram_queue"] = alerts.send_queued_telegrams(
        state.get("telegram_queue", []) + new_jobs, settings
    )
    state["email_queue"] = state.get("email_queue", []) + new_jobs

    # A late or failed email is sent on the next run.
    slot = alerts.latest_email_slot(
        datetime.now(ZoneInfo(settings["alerts"]["timezone"])), settings
    )
    email_sent = True
    if state.get("last_email_slot") != slot.isoformat():
        subject, text, body = alerts.build_email(state["email_queue"], slot)
        email_sent = alerts.send_gmail(subject, text, body, include_friend=True)
        if email_sent:
            state["email_queue"] = []
            state["last_email_slot"] = slot.isoformat()

    # Status alerts stay saved until one is delivered.
    pending = state.get("pending_alerts", []) + messages
    state["pending_alerts"] = [message for message in pending if not alerts.notify(message)]

    # A daily message proves the whole pipeline is still running.
    status_sent = True
    if state.get("last_heartbeat") != today:
        working = sum(
            "error" not in result and not result["empty"] for result in results.values()
        )
        status_sent = alerts.notify(
            f"Internship scraper is running: {working}/{len(companies)} companies OK."
        )
        if status_sent:
            state["last_heartbeat"] = today

    state_store.save_state(state)

    print(f"{len(new_jobs)} new jobs, {len(state['telegram_queue'])} awaiting Telegram.")
    if state["telegram_queue"] or state["pending_alerts"] or not status_sent or not email_sent:
        # Failing the run makes GitHub warn you and blocks the health ping.
        print("Some alerts weren't delivered and will be retried next run.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
