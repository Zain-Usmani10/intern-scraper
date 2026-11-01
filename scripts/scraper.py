"""Check career pages and send alerts for newly posted internships.

Usage:
    python scripts/scraper.py                Run normally.
    python scripts/scraper.py --dry-run      Show what was found. Sends nothing, saves nothing.
    python scripts/scraper.py --test-alert   Send a test message to each alert channel.
"""

import argparse
import asyncio
import html
import json
import os
import re
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_FILE = ROOT / "companies.json"
STATE_FILE = ROOT / "seen_jobs.json"

TIMEZONE = "America/Toronto"
DIGEST_HOURS = (8, 17)

MAX_PAGES_AT_ONCE = 5
PAGE_TIMEOUT_MS = 30_000
SETTLE_TIMEOUT_MS = 8_000
FAILURES_BEFORE_ALERT = 3
MAX_API_PAGES = 50
API_PAGE_DELAY_SECONDS = 1
RATE_LIMIT_WAITS_SECONDS = (5, 20)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# A link counts as a job posting if it matches this pattern. A company can
# replace it with its own "link_pattern" in companies.json.
DEFAULT_LINK_PATTERN = (
    r"/(jobs?|careers?|positions?|openings?|opportunities|requisitions?|vacancies)/[^/?#]+"
    r"|[?&](gh_jid|jobid|job_id|jid|reqid)="
    r"|/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

# Whole words only, so "internal" and "international" don't match. A company
# can turn this off with "skip_intern_filter": true in companies.json.
# This is broad on purpose: an extra alert is better than a missed internship.
INTERN_PATTERN = re.compile(
    r"\b("
    r"interns?|internships?|co-?ops?|students?|university|universities|campus"
    r"|early[\s-]careers?|apprentices?|apprenticeships?|trainees?"
    r"|summer[\s-](analysts?|associates?)"
    r")\b",
    re.IGNORECASE,
)

# Links ending in one of these are site pages, not postings.
NON_JOB_ENDINGS = {
    "alerts", "applications", "benefits", "faq", "join", "jobs", "login",
    "profile", "results", "saved", "search", "signin", "students", "teams",
}

TRACKING_PARAMS = {
    "ref", "referer", "referrer", "source", "src", "gh_src", "lever-source",
    "lever-origin", "fbclid", "gclid", "mc_cid", "mc_eid", "trk", "_ga",
}

BLOCKED_RESOURCES = {"image", "media", "font"}


def normalize_url(url):
    """Remove the parts of a URL that can change while the job stays the same."""
    parts = urllib.parse.urlsplit(url.strip())
    query = sorted(
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    )
    return urllib.parse.urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/"),
        urllib.parse.urlencode(query),
        "",
    ))


def clean_title(text):
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    return next((line for line in lines if line), "")


def extract_jobs(links, page_url, link_pattern=None):
    """Turn raw {href, text} links into a {normalized_url: title} dict."""
    pattern = re.compile(link_pattern or DEFAULT_LINK_PATTERN, re.IGNORECASE)
    page = normalize_url(page_url)
    jobs = {}

    for link in links:
        href = link.get("href") or ""
        if not href.lower().startswith("http"):
            continue

        url = normalize_url(href)
        ending = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1].lower()
        if url == page or ending in NON_JOB_ENDINGS or not pattern.search(url):
            continue

        title = clean_title(link.get("text"))
        if url not in jobs or (title and not jobs[url]):
            jobs[url] = title

    return {url: title or "New posting" for url, title in jobs.items()}


def keep_internships(jobs):
    """Check both title and URL, since some sites use a generic link title."""
    return {
        url: title
        for url, title in jobs.items()
        if INTERN_PATTERN.search(f"{title} {url}")
    }


def get_json(url):
    """Fetch JSON, waiting and retrying if the site says to slow down."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    for wait_seconds in (*RATE_LIMIT_WAITS_SECONDS, None):
        try:
            with urllib.request.urlopen(
                request, timeout=PAGE_TIMEOUT_MS / 1000
            ) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429 or wait_seconds is None:
                raise
            time.sleep(wait_seconds)


def eightfold_site(company):
    page_url = urllib.parse.urlsplit(company["url"])
    return f"{page_url.scheme}://{page_url.netloc}"


def eightfold_default_domain(url):
    return ".".join(urllib.parse.urlsplit(url).hostname.split(".")[-2:])


def eightfold_search_url(company, start):
    """Build the API URL using the filters from the company's career page URL."""
    page_url = urllib.parse.urlsplit(company["url"])
    domain = company.get("eightfold_domain") or eightfold_default_domain(company["url"])
    params = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(page_url.query, keep_blank_values=True)
        if key not in ("pid", "start", "domain")
    ]
    query = urllib.parse.urlencode([*params, ("domain", domain), ("start", start)])
    return f"{eightfold_site(company)}/api/pcsx/search?{query}"


def fetch_eightfold(company):
    """Read every result from an Eightfold career site's search API."""
    site = eightfold_site(company)
    jobs = {}
    for _ in range(MAX_API_PAGES):
        data = get_json(eightfold_search_url(company, len(jobs)))["data"]

        before = len(jobs)
        for position in data["positions"]:
            url = normalize_url(urllib.parse.urljoin(site, position["positionUrl"]))
            jobs[url] = clean_title(position["name"]) or "New posting"

        if len(jobs) == before or len(jobs) >= data["count"]:
            return jobs
        time.sleep(API_PAGE_DELAY_SECONDS)

    raise RuntimeError(f"more than {MAX_API_PAGES} pages of results")


def fetch_greenhouse(company):
    """Read every job on a Greenhouse board from its public API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company['board']}/jobs"
    data = get_json(url)
    return {
        normalize_url(job["absolute_url"]): clean_title(job["title"]) or "New posting"
        for job in data["jobs"]
    }


API_FETCHERS = {"eightfold": fetch_eightfold, "greenhouse": fetch_greenhouse}


async def scrape_api(limiter, company):
    async with limiter:
        try:
            fetcher = API_FETCHERS[company["type"]]
            all_jobs = await asyncio.to_thread(fetcher, company)
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}

    jobs = all_jobs
    if not company.get("skip_intern_filter"):
        jobs = keep_internships(all_jobs)
    return {"jobs": jobs, "empty": not all_jobs}


async def block_heavy_resources(route):
    if route.request.resource_type in BLOCKED_RESOURCES:
        await route.abort()
    else:
        await route.continue_()


async def scrape_company(browser_context, limiter, company):
    """Return {"jobs": {...}, "empty": bool} or {"error": "..."} on failure.

    "empty" means the page had no job links at all, which could be a broken
    page or a company with no openings. A page with other jobs but no
    internships is healthy and isn't marked empty.
    """
    async with limiter:
        page = await browser_context.new_page()
        try:
            await page.goto(
                company["url"], wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
            except PlaywrightTimeout:
                pass  # Some sites never go quiet. Use what has loaded so far.

            links = await page.eval_on_selector_all(
                "a[href]",
                "els => els.map(el => ({href: el.href, text: el.innerText}))",
            )
            all_jobs = extract_jobs(links, company["url"], company.get("link_pattern"))
            jobs = all_jobs
            if not company.get("skip_intern_filter"):
                jobs = keep_internships(all_jobs)
            return {"jobs": jobs, "empty": not all_jobs}
        except Exception as error:
            return {"error": f"{type(error).__name__}: {str(error).splitlines()[0]}"}
        finally:
            await page.close()


async def scrape_all(companies):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(user_agent=USER_AGENT)
        await context.route("**/*", block_heavy_resources)
        limiter = asyncio.Semaphore(MAX_PAGES_AT_ONCE)
        results = await asyncio.gather(*(
            scrape_api(limiter, company)
            if "type" in company
            else scrape_company(context, limiter, company)
            for company in companies
        ))
        await browser.close()
    return {company["name"]: result for company, result in zip(companies, results)}


def telegram_ready():
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def gmail_ready():
    return bool(os.getenv("GMAIL_ADDRESS") and os.getenv("GMAIL_APP_PASSWORD"))


def send_telegram(text):
    """Send one Telegram message. Return True if it was delivered."""
    if not telegram_ready():
        return False

    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    body = urllib.parse.urlencode({
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": text,
    }).encode()
    try:
        with urllib.request.urlopen(url, data=body, timeout=15) as response:
            return json.load(response).get("ok", False)
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        # Only the error type is logged because the URL contains the bot token.
        print(f"Telegram failed: {type(error).__name__}")
        return False


def send_gmail(subject, text, html=None, include_friend=False):
    """Send one email to yourself, and optionally BCC your friend.

    Return True if it was delivered.
    """
    if not gmail_ready():
        return False

    address = os.environ["GMAIL_ADDRESS"]
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = address
    message["To"] = address
    friend = os.getenv("FRIEND_EMAIL", "").strip()
    if include_friend and friend:
        message["Bcc"] = friend
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(address, os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
            server.send_message(message)
        return True
    except (smtplib.SMTPException, OSError) as error:
        print(f"Gmail failed: {type(error).__name__}: {error}")
        return False


def notify(text):
    """Send a status message by Telegram, using your email only as a backup."""
    return send_telegram(text) or send_gmail(clean_title(text)[:80], text)


def format_job(job):
    return f"{job['company']}\n{job['title']}\n{job['url']}"


def send_queued_telegrams(jobs):
    """Send each job to Telegram. Return the jobs that still need sending."""
    unsent = []
    for job in jobs:
        if not send_telegram(f"New internship\n\n{format_job(job)}"):
            unsent.append(job)
        time.sleep(1)  # Stay under Telegram's rate limit.
    return unsent


def latest_digest_slot(now):
    """Return the most recent scheduled email time at or before a local time."""
    slots = (
        (now - timedelta(days=days_ago)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        for days_ago in (0, 1)
        for hour in DIGEST_HOURS
    )
    return max(slot for slot in slots if slot <= now)


def build_digest(jobs, slot):
    """Return the subject, plain text, and HTML for a scheduled email."""
    count = len(jobs)
    date = f"{slot:%B} {slot.day}, {slot.year}"
    edition = "Morning Update" if slot.hour < 12 else "Evening Update"
    summary = (
        f"{count} new posting{'s' if count != 1 else ''} since the last update."
        if jobs
        else "No new postings since the last update."
    )
    subject = f"Internship {edition}: {count} New | {date}"

    by_company = {}
    for job in sorted(jobs, key=lambda job: (job["company"], job["title"])):
        by_company.setdefault(job["company"], []).append(job)

    text_parts = [f"Internship {edition}", date, "", summary]
    html_parts = [
        '<div style="font-family:Arial,sans-serif;color:#222;line-height:1.5;">',
        f'<h2 style="margin:0;">Internship {edition}</h2>',
        f'<p style="margin:4px 0 16px;color:#555;">{date}</p>',
        f"<p>{summary}</p>",
    ]
    for company, company_jobs in by_company.items():
        text_parts.extend(["", company])
        html_parts.append(
            f'<h3 style="margin:20px 0 6px;">{html.escape(company)}</h3>'
            '<ul style="margin:0;padding-left:20px;">'
        )
        for job in company_jobs:
            text_parts.append(f"- {job['title']}\n  {job['url']}")
            url = html.escape(job["url"], quote=True)
            html_parts.append(f'<li><a href="{url}">{html.escape(job["title"])}</a></li>')
        html_parts.append("</ul>")
    html_parts.append("</div>")

    return subject, "\n".join(text_parts), "".join(html_parts)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"companies": {}, "last_heartbeat": None}


def save_state(state):
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_file.replace(STATE_FILE)


def apply_results(state, results, now):
    """Update state from scrape results. Return new jobs and failure messages."""
    new_jobs = []
    messages = []

    for name, result in results.items():
        record = state["companies"].get(name)

        if "error" in result:
            print(f"[{name}] FAILED: {result['error']}")
            record = state["companies"].setdefault(name, {"failures": 0})
            record["failures"] = record.get("failures", 0) + 1
            if record["failures"] == FAILURES_BEFORE_ALERT:
                messages.append(f"Scraper problem: {name}\n{result['error']}")
            continue

        jobs = result["jobs"]
        print(f"[{name}] {len(jobs)} job links")

        if record is None or "seen" not in record:
            # First successful run: save what exists without alerting.
            failures = (record or {}).get("failures", 0)
            record = {"failures": failures, "seen": {url: now for url in jobs}}
            state["companies"][name] = record
            print(f"[{name}] Saved as baseline. No alerts sent.")
        else:
            new_jobs.extend(
                {"company": name, "title": title, "url": url}
                for url, title in jobs.items()
                if url not in record["seen"]
            )

        if result.get("empty"):
            record["failures"] += 1
            if record["failures"] == FAILURES_BEFORE_ALERT:
                messages.append(
                    f"No job links found: {name}\n"
                    "This is normal if there are no openings. "
                    "Otherwise, check the page."
                )
            continue

        if record["failures"] >= FAILURES_BEFORE_ALERT:
            messages.append(f"Scraper recovered: {name}")
        record["failures"] = 0

    return new_jobs, messages


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-alert", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    if args.test_alert:
        telegram = send_telegram("Test alert from your internship scraper.")
        sample = {
            "company": "Example Company",
            "title": "Sample Internship (Test)",
            "url": "https://example.com/jobs/1",
        }
        subject, text, body = build_digest(
            [sample], latest_digest_slot(datetime.now(ZoneInfo(TIMEZONE)))
        )
        gmail = send_gmail(f"Test: {subject}", text, body, include_friend=True)
        print(f"Telegram: {'sent' if telegram else 'NOT sent'}")
        print(f"Gmail: {'sent' if gmail else 'NOT sent'}")
        return 0 if telegram or gmail else 1

    if not args.dry_run and not (telegram_ready() or gmail_ready()):
        print("No alert channel is configured. Add your settings to .env.")
        return 1

    companies = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
    results = asyncio.run(scrape_all(companies))

    if args.dry_run:
        for name, result in results.items():
            if "error" in result:
                print(f"\n{name}: FAILED: {result['error']}")
                continue
            print(f"\n{name}: {len(result['jobs'])} job links")
            for url, title in result["jobs"].items():
                print(f"  {title}\n    {url}")
        return 0

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = load_state()
    new_jobs, messages = apply_results(state, results, now)

    # New jobs wait in these saved queues until each one is delivered.
    for job in new_jobs:
        state["companies"][job["company"]]["seen"][job["url"]] = now
    state["telegram_queue"] = send_queued_telegrams(
        state.get("telegram_queue", []) + new_jobs
    )
    state["digest_queue"] = state.get("digest_queue", []) + new_jobs

    # A late or failed email is sent on the next run.
    slot = latest_digest_slot(datetime.now(ZoneInfo(TIMEZONE)))
    digest_sent = True
    if state.get("last_digest_slot") != slot.isoformat():
        subject, text, body = build_digest(state["digest_queue"], slot)
        digest_sent = send_gmail(subject, text, body, include_friend=True)
        if digest_sent:
            state["digest_queue"] = []
            state["last_digest_slot"] = slot.isoformat()

    # Status alerts stay in the saved state until one is delivered.
    pending = state.get("pending_alerts", []) + messages
    state["pending_alerts"] = [message for message in pending if not notify(message)]

    # A daily message proves the whole pipeline is still running.
    today = now[:10]
    status_sent = True
    if state.get("last_heartbeat") != today:
        total = len(companies)
        working = sum(
            "error" not in result and not result["empty"]
            for result in results.values()
        )
        status_sent = notify(
            f"Internship scraper is running: {working}/{total} pages OK."
        )
        if status_sent:
            state["last_heartbeat"] = today

    save_state(state)

    print(f"{len(new_jobs)} new jobs, {len(state['telegram_queue'])} awaiting Telegram.")
    if (
        state["telegram_queue"]
        or state["pending_alerts"]
        or not status_sent
        or not digest_sent
    ):
        # Failing the run makes GitHub warn you and blocks the health ping.
        print("Some alerts weren't delivered and will be retried next run.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
