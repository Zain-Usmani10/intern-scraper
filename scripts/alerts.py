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


def format_job(job):
    lines = [job["company"], job["title"]]
    if job.get("location"):
        lines.append(job["location"])
    lines.append(job["url"])
    return "\n".join(lines)


def send_queued_telegrams(jobs, settings):
    """Send each job to Telegram. Return the jobs that still need sending."""
    unsent = []
    for job in jobs:
        if not send_telegram(f"New internship\n\n{format_job(job)}"):
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


def build_email(jobs, slot):
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
            location = job.get("location") or ""
            text_parts.append(
                f"- {job['title']}" + (f" ({location})" if location else "") + f"\n  {job['url']}"
            )
            url = html.escape(job["url"], quote=True)
            place = (
                f' <span style="color:#666;">({html.escape(location)})</span>' if location else ""
            )
            html_parts.append(
                f'<li><a href="{url}">{html.escape(job["title"])}</a>{place}</li>'
            )
        html_parts.append("</ul>")
    html_parts.append("</div>")

    return subject, "\n".join(text_parts), "".join(html_parts)
