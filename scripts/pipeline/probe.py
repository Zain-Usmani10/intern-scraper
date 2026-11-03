"""Step 2a: load the careers page in Chromium and record what it uses.

The result is saved to data/tmp/evidence.json. Detection reads it, and so
does Claude if detection fails.
"""

import re
import urllib.parse

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

import config
from methods.browser_common import extract_jobs
from methods.common import USER_AGENT

KNOWN_SYSTEMS = (
    r"greenhouse\.io|ashbyhq\.com|lever\.co|myworkdayjobs\.com|eightfold\.ai|/api/pcsx/"
    r"|icims\.com|amazon\.jobs|smartrecruiters\.com|successfactors|taleo|jobvite"
    r"|workable\.com|rippling\.com|bamboohr\.com|avature|phenom|oraclecloud\.com"
    r"|workforcenow\.adp\.com|applytojob\.com|talentbrew|radancy"
)
SYSTEM_REFERENCE = re.compile(rf"[\w.-]*(?:{KNOWN_SYSTEMS})[^\"'\s<>)\\]{{0,80}}", re.I)
VISIBLE_TOTAL = re.compile(
    r"\b([\d,]{1,7})\s+(?:open\s+)?(?:jobs?|results?|positions?|roles?|openings?)\b", re.I
)
SKIPPED_HOSTS = re.compile(
    r"google-analytics|googletagmanager|doubleclick|cookielaw|onetrust|cookieyes|segment"
    r"|sentry|hotjar|datadog|facebook|linkedin|mixpanel|hubspot|qualtrics|clarity", re.I
)

# Returns the first visible, enabled control that leads to more results.
FIND_MORE_RESULTS = r"""
() => {
  const more = /^(go to )?next( page| jobs| results)?\b|^navigate_next$|^load more|^show more (jobs|results|positions)|^see more (jobs|results)|^view more (jobs|results)|^[›»>]$/i;
  const ignore = /slide|image|photo|video|story|testimonial|filter|categor/i;
  for (const control of document.querySelectorAll('a, button, [role="button"]')) {
    const label = (control.getAttribute('aria-label') || control.innerText || control.title || '').trim();
    const disabled = control.disabled || control.getAttribute('aria-disabled') === 'true'
      || /disabled/i.test(control.className || '');
    if (more.test(label) && !ignore.test(label) && !disabled && control.getClientRects().length) {
      return {label, href: control.href || null};
    }
  }
  const relNext = document.querySelector('a[rel="next"]');
  return relNext ? {label: 'rel=next', href: relNext.href} : null;
}
"""


def inspect(company, url, settings):
    """Return evidence about the page and save it to data/tmp/evidence.json."""
    requests = []
    timeout_ms = settings["scraping"]["request_timeout_seconds"] * 1000

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_context(user_agent=USER_AGENT).new_page()

            def record(response):
                try:
                    request = response.request
                    if request.resource_type not in ("xhr", "fetch", "document"):
                        return
                    host = urllib.parse.urlsplit(response.url).hostname or ""
                    if SKIPPED_HOSTS.search(host):
                        return
                    try:
                        body = (request.post_data or "")[:300]
                    except UnicodeDecodeError:
                        body = "<binary request body>"
                    requests.append({
                        "method": request.method,
                        "url": response.url[:400],
                        "status": response.status,
                        "type": response.headers.get("content-type", "")[:40],
                        "body": body,
                    })
                except Exception:
                    pass  # One odd request must never stop the inspection.

            page.on("response", record)
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state(
                    "networkidle", timeout=settings["scraping"]["page_settle_seconds"] * 1000
                )
            except PlaywrightTimeout:
                pass

            links = page.eval_on_selector_all(
                "a[href]", "els => els.map(el => ({href: el.href, text: el.innerText}))"
            )
            more_results = page.evaluate(FIND_MORE_RESULTS)
            body_text = page.inner_text("body")
            html = page.content()
            frames = [frame.url for frame in page.frames[1:] if frame.url.startswith("http")]

            links_before = len(links)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2500)
            links_after = page.eval_on_selector_all("a[href]", "els => els.length")

            evidence = {
                "company": company,
                "careers_url": url,
                "final_url": page.url,
                "status": response.status if response else None,
                "page_title": page.title()[:120],
                "system_references": sorted(set(
                    SYSTEM_REFERENCE.findall(html + " " + " ".join(frames))
                ))[:40],
                "frames": frames[:10],
                "api_requests": [
                    item for item in requests
                    if "json" in item["type"] or item["method"] == "POST"
                ][:40],
                "link_count": len(links),
                "links": [link["href"] for link in links][:400],
                "job_like_links": [
                    f"{job['title'][:60]} | {link_url}"
                    for link_url, job in list(extract_jobs(links, page.url).items())[:30]
                ],
                "more_results_control": more_results,
                "loads_more_on_scroll": links_after > links_before,
                "visible_totals": VISIBLE_TOTAL.findall(body_text)[:10],
            }
        finally:
            browser.close()

    saved = {key: value for key, value in evidence.items() if key != "links"}
    saved["candidates_tried"] = []
    config.write_json(config.EVIDENCE_FILE, saved)
    return evidence


def record_tried(report):
    """Add a validation result to evidence.json so Claude can see it."""
    evidence = config.read_json(config.EVIDENCE_FILE, default={})
    evidence.setdefault("candidates_tried", []).append({
        "method": report["method"],
        "params": report["params"],
        "status": report["status"],
        "reason": report["reason"],
    })
    config.write_json(config.EVIDENCE_FILE, evidence)
