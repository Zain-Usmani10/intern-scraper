"""Gem: reads every job from the public job board API at api.gem.com."""

from methods.common import job, listing, normalize_url, request_json, require


def fetch(params, settings):
    require(params, "board")
    postings = request_json(
        f"https://api.gem.com/job_board/v0/{params['board']}/job_posts/", settings
    )
    jobs = {}
    for posting in postings:
        places = [(office.get("location") or {}).get("name") for office in posting.get("offices") or []]
        jobs[normalize_url(posting["absolute_url"])] = job(
            posting["title"], places or [(posting.get("location") or {}).get("name")]
        )
    # The API has no total, but returns the whole board in one response.
    return listing(jobs)
