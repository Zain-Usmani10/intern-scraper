"""Browser page: loads one page in Chromium and collects job links. Last resort."""

from methods.browser_common import browser_page, extract_jobs, load, page_links
from methods.common import listing, require


def fetch(params, settings):
    require(params, "url")
    with browser_page(settings) as page:
        load(page, params["url"], settings)
        links = page_links(page)
    # A single page reports no total, so adding one needs manual approval.
    return listing(extract_jobs(links, params["url"], params.get("link_pattern")))
