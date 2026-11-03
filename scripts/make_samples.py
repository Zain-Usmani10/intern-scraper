"""Write the approved alert examples to sample/.

tests/test_alert_format.py fails if the alerts stop matching these files.
Run this only when you mean to change the format:
    python scripts/make_samples.py
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

import alerts
import config

SAMPLE_DIR = config.ROOT / "sample"
SAMPLE_SLOT = datetime(2026, 11, 3, 8, 30, tzinfo=ZoneInfo("America/Toronto"))


def samples():
    """The subject, plain text, HTML, and one Telegram alert for SAMPLE_JOBS."""
    subject, text, body = alerts.build_email(alerts.SAMPLE_JOBS, SAMPLE_SLOT)
    return {
        "email.txt": f"Subject: {subject}\n\n{text}\n",
        "email.html": body + "\n",
        "telegram.txt": alerts.format_job(alerts.SAMPLE_JOBS[2]) + "\n",
    }


def main():
    SAMPLE_DIR.mkdir(exist_ok=True)
    files = samples()
    for name, content in files.items():
        (SAMPLE_DIR / name).write_text(content, encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(files["email.html"])
        page.pdf(path=str(SAMPLE_DIR / "email.pdf"), format="Letter",
                 margin={"top": "0.6in", "bottom": "0.6in", "left": "0.6in", "right": "0.6in"})
        browser.close()
    print(f"Wrote {', '.join([*files, 'email.pdf'])} to {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
