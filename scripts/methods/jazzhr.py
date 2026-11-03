"""JazzHR: reads the board at COMPANY.applytojob.com, which lists every job on one page."""

import html
import re

from methods.common import job, listing, normalize_url, request_text, require

LINK = re.compile(r'<a href="(https://[\w-]+\.applytojob\.com/apply/\w+/[^"]*)"[^>]*>(.*?)</a>', re.S)
LOCATION = re.compile(r"fa-map-marker[^>]*></i>([^<]+)<")


def fetch(params, settings):
    require(params, "company")
    page = request_text(f"https://{params['company']}.applytojob.com/apply", settings)
    jobs = {}
    # Each job is one list item: a title link, then its location.
    for item in page.split('class="list-group-item"')[1:]:
        link = LINK.search(item)
        if not link:
            continue
        location = LOCATION.search(item)
        jobs[normalize_url(link.group(1))] = job(
            html.unescape(link.group(2)),
            [html.unescape(location.group(1)).strip()] if location else [],
        )
    # The board has no pagination, so this is the whole list.
    return listing(jobs)
