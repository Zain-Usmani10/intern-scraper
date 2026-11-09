"""Telegram messages, Gmail updates, and the twice-daily email format."""

import html
import json
import os
import smtplib
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from email.message import EmailMessage

from methods.common import clean_title


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


def send_gmail(subject, text, html_body=None, include_friend=False):
    """Send one email to yourself, and optionally BCC your friend."""
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
    if html_body:
        message.add_alternative(html_body, subtype="html")
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


# The alert formats are locked by tests/test_alert_format.py, which compares
# them with the approved examples in sample/. To change them on purpose, run
# scripts/make_samples.py after editing, and commit the new samples.

NO_COUNTRY = "Location not listed"

# Dummy jobs for --test-alert and the samples: 3 companies, one with Canadian,
# US, and unlisted jobs.
SAMPLE_JOBS = [
    {"company": company, "title": title, "location": location, "country": country,
     "url": f"https://example.com/jobs/{number}"}
    for number, (company, title, location, country) in enumerate([
        ("Northwind Robotics", "Embedded Firmware Intern (Summer 2027)", "Toronto, ON", "Canada"),
        ("Northwind Robotics", "Hardware Validation Co-op", "Waterloo, ON", "Canada"),
        ("Northwind Robotics", "Robotics Software Intern", "Boston, MA", "United States"),
        ("Northwind Robotics", "FPGA Design Intern", "Austin, TX", "United States"),
        ("Northwind Robotics", "Controls Engineering Intern", "Remote", ""),
        ("Maple Silicon", "ASIC Verification Intern", "Ottawa, ON", "Canada"),
        ("Maple Silicon", "Analog Design Co-op (8 months)", "Kanata, ON", "Canada"),
        ("Maple Silicon", "Test Engineering Student", "Ottawa, ON", "Canada"),
        ("Aurora Photonics", "Optical Systems Intern", "Vancouver, BC", "Canada"),
        ("Aurora Photonics", "Data Pipeline Co-op", "Burnaby, BC", "Canada"),
    ], 1)
]


def country_label(job):
    return job.get("country") or NO_COUNTRY


def format_job(job):
    """One Telegram alert, casual: company and country, then the job."""
    lines = ["🚨 New internship!", f"{job['company']} · {country_label(job)}", "", job["title"]]
    if job.get("location"):
        lines.append(f"📍 {job['location']}")
    lines.append(f"👉 {job['url']}")
    return "\n".join(lines)


def send_queued_telegrams(jobs, settings):
    """Send each job to Telegram. Return the jobs that still need sending."""
    unsent = []
    for job in jobs:
        if not send_telegram(format_job(job)):
            unsent.append(job)
        time.sleep(settings["alerts"]["telegram_delay_seconds"])
    return unsent


def latest_email_slot(now, settings):
    """Return the most recent scheduled email time at or before a local time."""
    times = [tuple(map(int, text.split(":"))) for text in settings["alerts"]["email_times"]]
    slots = (
        (now - timedelta(days=days_ago)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        for days_ago in (0, 1)
        for hour, minute in times
    )
    return max(slot for slot in slots if slot <= now)


def group_jobs(jobs):
    """{company: {country: [jobs]}}, sorted, with unknown countries last."""
    grouped = {}
    for job in sorted(jobs, key=lambda job: (job["company"].casefold(), job["title"].casefold())):
        grouped.setdefault(job["company"], {}).setdefault(country_label(job), []).append(job)
    return {
        company: dict(sorted(countries.items(), key=lambda item: (item[0] == NO_COUNTRY, item[0])))
        for company, countries in grouped.items()
    }


def build_email(jobs, slot):
    """Return the subject, plain text, and HTML for a scheduled email.

    Layout: numbered companies, each country in bold, then numbered jobs with
    a linked title and the location.
    """
    count = len(jobs)
    date = f"{slot:%B} {slot.day}, {slot.year}"
    edition = "Morning Update" if slot.hour < 12 else "Evening Update"
    summary = (
        f"{count} new posting{'s' if count != 1 else ''} since the last update."
        if jobs
        else "No new postings since the last update."
    )
    subject = f"Internship {edition}: {count} New | {date}"

    text = [f"Internship {edition}", date, "", summary]
    page = [
        '<div style="font-family:Arial,sans-serif;font-size:14px;">',
        f'<h2 style="font-size:20px;margin:0;">Internship {edition}</h2>',
        f"<p>{date}<br>{summary}</p>",
    ]
    for number, (company, countries) in enumerate(group_jobs(jobs).items(), 1):
        total = sum(len(country_jobs) for country_jobs in countries.values())
        text += ["", f"{number}. {company} ({total})"]
        page.append(f'<h3 style="font-size:17px;margin:18px 0 4px;">{number}. {html.escape(company)} ({total})</h3>')
        for country, country_jobs in countries.items():
            text.append(f"   {country} ({len(country_jobs)})")
            page.append(f'<p style="margin:8px 0 2px;"><b>{html.escape(country)} ({len(country_jobs)})</b></p><ol style="margin:0;">')
            for position, job in enumerate(country_jobs, 1):
                location = job.get("location") or ""
                text.append(f"      {position}. {job['title']}" + (f" - {location}" if location else ""))
                text.append(f"         {job['url']}")
                place = f" - {html.escape(location)}" if location else ""
                page.append(f'<li><a href="{html.escape(job["url"], quote=True)}"><b>{html.escape(job["title"])}</b></a>{place}</li>')
            page.append("</ol>")
    page.append("</div>")

    return subject, "\n".join(text), "\n".join(page)
