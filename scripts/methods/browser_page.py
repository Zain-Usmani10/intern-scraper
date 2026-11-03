"""Browser page: loads one page in Chromium and collects job links."""

from methods.browser_common import browser_page, extract_jobs, load, page_links, reported_total
from methods.common import listing, require


def fetch(params, settings):
    require(params, "url")
    with browser_page(settings) as page:
        load(page, params["url"], settings)
        total = reported_total(page, params.get("total_regex"))
        links = page_links(page)
    # Without total_regex there's no total, so adding the company needs approval.
    return listing(extract_jobs(links, params["url"], params.get("link_pattern")), total)
