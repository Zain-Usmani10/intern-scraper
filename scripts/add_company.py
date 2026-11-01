"""Validate a company on this computer, then add it to companies.json.

Usage:
    python scripts/add_company.py "Company Name" "CAREER_PAGE_URL"

Nothing is saved unless every check passes and you confirm the results.
Add --allow-first-page-only to accept a generic page with more results than
the scraper can reach. Use it only for a page sorted newest first.
"""

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.error
import urllib.parse

from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

import scraper

MAX_TITLES_SHOWN = 40
SECONDS_BETWEEN_SCRAPES = 3
SCROLL_WAIT_MS = 2_500

LOGIN_PATH = re.compile(r"/(login|log-in|signin|sign-in|sso|auth)(/|$)", re.IGNORECASE)
GREENHOUSE_LINK = re.compile(r"greenhouse\.io/([\w-]+)/jobs/\d+", re.IGNORECASE)

# Returns the first visible, enabled control that leads to more results.
FIND_MORE_RESULTS_CONTROL = r"""
() => {
  const label = /^(next|next page|next jobs|load more|show more|see more|view more)\b|^[›»>]$/i;
  const controls = document.querySelectorAll('a, button, [role="button"]');
  for (const control of controls) {
    const text = (control.getAttribute('aria-label') || control.innerText || '').trim();
    const disabled = control.disabled
      || control.getAttribute('aria-disabled') === 'true'
      || /disabled/i.test(control.className || '');
    if (label.test(text) && !disabled && control.getClientRects().length) return text;
  }
  return document.querySelector('a[rel="next"]') ? 'rel=next link' : null;
}
"""


class CheckFailed(Exception):
    pass


def passed(message):
    print(f"PASS  {message}")


def greenhouse_board_from_url(url):
    parts = urllib.parse.urlsplit(url)
    if not (parts.hostname or "").endswith("greenhouse.io"):
        return None
    board = urllib.parse.parse_qs(parts.query).get("for", [""])[0]
    path_parts = [part for part in parts.path.split("/") if part]
    if not board and path_parts and path_parts[0] != "embed":
        board = path_parts[0]
    return board or None


async def inspect_page(url):
    """Load a page and collect what's needed to identify and test it."""
    search_requests = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(user_agent=scraper.USER_AGENT)
        await context.route("**/*", scraper.block_heavy_resources)
        page = await context.new_page()
        page.on(
            "request",
            lambda request: search_requests.append(request.url)
            if "/api/pcsx/search" in request.url
            else None,
        )

        response = await page.goto(
            url, wait_until="domcontentloaded", timeout=scraper.PAGE_TIMEOUT_MS
        )
        try:
            await page.wait_for_load_state(
                "networkidle", timeout=scraper.SETTLE_TIMEOUT_MS
            )
        except PlaywrightTimeout:
            pass

        count_links = "els => els.length"
        links_before = await page.eval_on_selector_all("a[href]", count_links)
        hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
        more_results = await page.evaluate(FIND_MORE_RESULTS_CONTROL)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(SCROLL_WAIT_MS)
        links_after = await page.eval_on_selector_all("a[href]", count_links)

        info = {
            "status": response.status if response else None,
            "final_url": page.url,
            "hrefs": hrefs,
            "more_results": more_results,
            "loads_on_scroll": links_after > links_before,
            "search_requests": search_requests,
        }
        await browser.close()
    return info


def build_entry(name, url, info):
    """Choose the most reliable way to read this company's jobs."""
    board = greenhouse_board_from_url(url) or greenhouse_board_from_url(info["final_url"])
    if not board:
        match = GREENHOUSE_LINK.search(" ".join(info["hrefs"]))
        board = match.group(1) if match else None
    if board:
        return {"name": name, "type": "greenhouse", "board": board}

    if info["search_requests"]:
        entry = {"name": name, "type": "eightfold", "url": info["final_url"]}
        query = urllib.parse.urlsplit(info["search_requests"][0]).query
        domain = urllib.parse.parse_qs(query).get("domain", [""])[0]
        if domain and domain != scraper.eightfold_default_domain(info["final_url"]):
            entry["eightfold_domain"] = domain
        return entry

    return {"name": name, "url": url}


def reject_duplicates(companies, entry):
    source = entry.get("board") or entry.get("url")
    for company in companies:
        if company["name"].casefold() == entry["name"].casefold():
            raise CheckFailed(f'"{company["name"]}" is already in companies.json')
        if source in (company.get("board"), company.get("url")):
            raise CheckFailed(f'This source is already used by "{company["name"]}"')


def check_page_loaded(info):
    if info["status"] is None or info["status"] >= 400:
        raise CheckFailed(f"The page returned HTTP {info['status']}")
    if LOGIN_PATH.search(urllib.parse.urlsplit(info["final_url"]).path):
        raise CheckFailed(f"The page redirected to a login screen: {info['final_url']}")
    passed(f"Page is live (HTTP {info['status']})")


def check_api_complete(entry):
    """Compare what the scraper reads with the total reported by the API."""
    if entry["type"] == "eightfold":
        reported = scraper.get_json(scraper.eightfold_search_url(entry, 0))["data"]["count"]
    else:
        url = f"https://boards-api.greenhouse.io/v1/boards/{entry['board']}/jobs"
        reported = scraper.get_json(url)["meta"]["total"]

    time.sleep(scraper.API_PAGE_DELAY_SECONDS)
    found = len(scraper.API_FETCHERS[entry["type"]](entry))
    if found != reported:
        raise CheckFailed(f"Read {found} of the {reported} jobs the site reports")
    passed(f"All listings reachable ({found} of {reported} reported by the site)")


def check_generic_page_complete(info, allow_first_page_only):
    problems = []
    if info["more_results"]:
        problems.append(f'it has a "{info["more_results"]}" control')
    if info["loads_on_scroll"]:
        problems.append("more links load as you scroll")

    if problems and not allow_first_page_only:
        raise CheckFailed(
            f"The scraper can only read part of this page: {' and '.join(problems)}. "
            "Support for this site must be added first."
        )
    if problems:
        print(f"WARN  Accepted with first-page-only access: {' and '.join(problems)}")
    else:
        passed("No further pages or scroll loading detected")
    print("NOTE  This site reports no total, so compare the count below with the page.")


def scrape_entry(entry):
    return asyncio.run(scraper.scrape_all([entry]))[entry["name"]]


def check_stable_results(entry):
    first = scrape_entry(entry)
    time.sleep(SECONDS_BETWEEN_SCRAPES)
    second = scrape_entry(entry)

    for result in (first, second):
        if "error" in result:
            raise CheckFailed(f"The scraper failed: {result['error']}")
        if result["empty"]:
            raise CheckFailed("The scraper found no job links on this page")
    if set(first["jobs"]) != set(second["jobs"]):
        raise CheckFailed("Two scrapes returned different jobs, so links aren't stable")

    passed("Two scrapes returned the same jobs")
    return first["jobs"]


def show_jobs(entry, jobs):
    print(f"\nInternships found: {len(jobs)}")
    for title in sorted(jobs.values())[:MAX_TITLES_SHOWN]:
        print(f"  {title}")
    if len(jobs) > MAX_TITLES_SHOWN:
        print(f"  ...and {len(jobs) - MAX_TITLES_SHOWN} more")
    if not jobs:
        print("  None right now. Confirm this matches the site.")
    if entry.get("type") == "greenhouse":
        print("\nGreenhouse mode checks every location, even if your URL had filters.")


def save_entry(companies, entry):
    temp_file = scraper.COMPANIES_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps([*companies, entry], indent=2) + "\n", encoding="utf-8"
    )
    temp_file.replace(scraper.COMPANIES_FILE)


def validate(name, url, companies, allow_first_page_only):
    info = asyncio.run(inspect_page(url))
    check_page_loaded(info)

    entry = build_entry(name, url, info)
    passed(f"Platform: {entry.get('type', 'generic page')}")
    reject_duplicates(companies, entry)

    if "type" in entry:
        check_api_complete(entry)
    else:
        check_generic_page_complete(info, allow_first_page_only)

    return entry, check_stable_results(entry)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name")
    parser.add_argument("url")
    parser.add_argument("--allow-first-page-only", action="store_true")
    args = parser.parse_args()

    sys.stdout.reconfigure(errors="replace")
    name = args.name.strip()
    if not name:
        print("FAIL  The company name is empty.")
        return 1
    if urllib.parse.urlsplit(args.url).scheme not in ("http", "https"):
        print("FAIL  The URL must start with http:// or https://")
        return 1

    companies = json.loads(scraper.COMPANIES_FILE.read_text(encoding="utf-8"))
    try:
        entry, jobs = validate(name, args.url, companies, args.allow_first_page_only)
    except (CheckFailed, urllib.error.URLError, TimeoutError, KeyError) as error:
        print(f"FAIL  {error}\n\nNot added. companies.json was not changed.")
        return 1
    except Exception as error:
        print(f"FAIL  {type(error).__name__}: {str(error).splitlines()[0]}")
        print("\nNot added. companies.json was not changed.")
        return 1

    show_jobs(entry, jobs)
    if input(f"\nAdd {name}? Type y to confirm: ").strip().lower() != "y":
        print("Not added. companies.json was not changed.")
        return 1

    save_entry(companies, entry)
    print(f"\nAdded {name}. To send it to GitHub:")
    print("  git add companies.json")
    print(f'  git commit -m "Add {name}"')
    print("  git pull --rebase origin main")
    print("  git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
