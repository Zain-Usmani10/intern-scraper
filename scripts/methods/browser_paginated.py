"""Browser paginated: loads numbered result pages until no new job links appear."""

import re
import time
import urllib.parse

from methods.browser_common import browser_page, extract_jobs, load, page_links
from methods.common import listing, require


def with_page(url, param, value):
    parts = urllib.parse.urlsplit(url)
    query = [
        (key, val)
        for key, val in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key != param
    ]
    query.append((param, str(value)))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def reported_total(page, total_regex):
    if not total_regex:
        return None
    match = re.search(total_regex, page.inner_text("body"), re.IGNORECASE)
    if not match:
        raise RuntimeError("total_regex didn't match the first page")
    return int(re.sub(r"[^\d]", "", match.group(1)))


def fetch(params, settings):
    require(params, "url", "page_param")
    first_page = int(params.get("first_page", 1))
    step = int(params.get("page_step", 1))
    jobs = {}
    total = None

    with browser_page(settings) as page:
        for index in range(settings["scraping"]["max_browser_pages"]):
            url = with_page(params["url"], params["page_param"], first_page + index * step)
            load(page, url, settings)
            if index == 0:
                total = reported_total(page, params.get("total_regex"))

            found = extract_jobs(page_links(page), url, params.get("link_pattern"))
            new = {key: value for key, value in found.items() if key not in jobs}
            if not new:
                return listing(jobs, total)
            jobs.update(new)
            if total is not None and len(jobs) >= total:
                return listing(jobs, total)
            time.sleep(settings["scraping"]["api_page_delay_seconds"])

    raise RuntimeError("More result pages than max_browser_pages allows")
