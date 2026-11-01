# Internship Scraper Plan

**Goal:** Get a phone alert within an hour when a tracked company posts a new internship, at no cost.

**Status:** Planning. Nothing built yet.

## Current Setup

| Area | Current choice |
|---|---|
| Input | Manual list of career page URLs already filtered to internships |
| Scraper | Python script using one shared Playwright scraper |
| New job detection | Extract job links, normalize them, and compare with the seen list |
| Hosting | GitHub Actions on `ubuntu-latest` |
| Trigger | cron-job.org calls GitHub's `workflow_dispatch` API |
| Schedule | Every 20 minutes, 8am-5pm, plus one run at 8pm |
| Saved state | JSON file committed back to the repo |
| Notifications | Telegram bot |
| Failure alerts | Alert on page errors or zero job links, plus a daily "still alive" message |

## Pipeline

1. cron-job.org triggers the GitHub Actions workflow.
2. The script loads each URL, with up to 5 pages at once.
3. It extracts and normalizes the job links.
4. It compares them with the seen list.
5. It sends a Telegram alert for each new job.
6. It commits the updated seen list.

The first run saves existing jobs without sending alerts.

## Pros and Cons

| Choice | Pros | Cons |
|---|---|---|
| Filtered URLs + Playwright | Simple list, no need to know each ATS, handles JavaScript pages | Slower than APIs, some sites need custom rules or may block it |
| GitHub Actions | No server to manage | Private repos have a minute limit, and runs use data center IPs |
| cron-job.org trigger | On-time runs, timezone setting, avoids GitHub's scheduler delays | One more service and access token to manage |
| JSON seen list | Simple, free, easy to inspect | Adds a commit to the repo on each change |
| Telegram | Free, instant, can include apply links | Requires a short bot setup |
| 8am-5pm + 8pm schedule | Uses fewer runs | Jobs posted after 5pm can wait up to 3 hours, missing the 1-hour goal |

## GitHub Actions Usage

- Public repo: standard runners are free, but the code and company list are visible.
- Private repo: 3,000 minutes allows about 3.4 minutes per run on the current daily schedule (about 870 runs per month).
- GitHub rounds each job up to a full minute.
- Estimated run time is about 2 minutes for 30 pages at 5 at a time. Confirm this with real runs.

## Fallbacks

- Use a site's JSON API or a custom rule if the shared scraper is unreliable there.
- Move to an Oracle Cloud Always Free VM if GitHub Actions gets blocked by too many sites.

## Open Decisions

- [ ] Public or private repo?
- [ ] Daily or weekdays only?
- [ ] Stop regular runs at 5pm or continue through 8pm?
- [ ] Which timezone should the schedule use?
- [ ] Which company URLs go on the first list?

## Build Steps

1. Scrape a few test URLs locally and save the seen list.
2. Add Telegram alerts.
3. Add failure alerts and the daily "still alive" message.
4. Deploy to GitHub Actions and connect cron-job.org.
5. Add the full URL list and check real run times.
