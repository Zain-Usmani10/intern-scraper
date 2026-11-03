"""Chromium helpers shared by the two browser methods."""

import re
import urllib.parse
from contextlib import contextmanager

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from methods.common import USER_AGENT, clean_title, normalize_url

# A link counts as a job posting if it matches this, unless the company sets
# its own "link_pattern".
DEFAULT_LINK_PATTERN = (
    r"/(jobs?|careers?|positions?|openings?|opportunities|requisitions?|vacancies)/[^/?#]+"
    r"|[?&](gh_jid|jobid|job_id|jid|reqid)="
    r"|/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

# Links ending in one of these are site pages, not postings.
NON_JOB_ENDINGS = {
    "alerts", "applications", "benefits", "faq", "join", "jobs", "login",
    "profile", "results", "saved", "search", "signin", "students", "teams",
}

BLOCKED_RESOURCES = {"image", "media", "font"}


@contextmanager
def browser_page(settings):
    """Yield one Chromium page that skips images, video, and fonts."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(user_agent=USER_AGENT)
            context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in BLOCKED_RESOURCES
                else route.continue_(),
            )
            yield context.new_page()
        finally:
            browser.close()


def load(page, url, settings):
    """Open a URL and wait for the page to settle. Return the HTTP status."""
    timeout_ms = settings["scraping"]["request_timeout_seconds"] * 1000
    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state(
            "networkidle", timeout=settings["scraping"]["page_settle_seconds"] * 1000
        )
    except PlaywrightTimeout:
        pass  # Some sites never go quiet. Use what has loaded.
    status = response.status if response else None
    if status is None or status >= 400:
        raise RuntimeError(f"page returned HTTP {status}")
    return status


# For each link: its text, or the job card's heading when the link only says
# something like "Learn more", plus the card's text for location filtering.
LINK_DETAILS = r"""
els => els.map(el => {
  const generic = /^(learn more|apply( now)?|view( job| details| role| position)?|details|read more|see more|see full( role)? description|more info)?$/i;
  let text = (el.innerText || '').trim();
  let card = el;
  for (let depth = 0; depth < 6 && card.parentElement; depth++) {
    card = card.parentElement;
    if (card.querySelector('h1, h2, h3, h4, [role="heading"]')) break;
  }
  if (generic.test(text)) {
    const heading = card.querySelector('h1, h2, h3, h4, [role="heading"]');
    const label = (el.getAttribute('aria-label') || el.title || '')
      .replace(/^(learn more about|apply (now )?(for|to)|view( job)?( details)?( for)?)\s*/i, '');
    text = (heading && heading.innerText.trim()) || label.trim();
  }
  const cardText = card === el ? '' : (card.innerText || '').replace(/\s+/g, ' ').slice(0, 400);
  return {href: el.href, text, card: cardText};
})
"""


def page_links(page):
    return page.eval_on_selector_all("a[href]", LINK_DETAILS)


def extract_jobs(links, page_url, link_pattern=None):
    """Turn raw {href, text} links into {url: {title, locations}}."""
    pattern = re.compile(link_pattern or DEFAULT_LINK_PATTERN, re.IGNORECASE)
    page = normalize_url(page_url)
    found = {}

    for link in links:
        href = link.get("href") or ""
        if not href.lower().startswith("http"):
            continue
        url = normalize_url(href)
        ending = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1].lower()
        if url == page or ending in NON_JOB_ENDINGS or not pattern.search(url):
            continue
        title = clean_title(link.get("text"))
        if url not in found or (title and not found[url]["title"]):
            found[url] = {"title": title, "card": link.get("card") or ""}

    # Pages don't give a location field. The card text is used to drop jobs
    # that clearly name another country.
    return {
        url: {"title": item["title"] or "New posting", "locations": [],
              "location_hint": item["card"]}
        for url, item in found.items()
    }
