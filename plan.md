# Internship Scraper Plan

**Goal:** Get a phone alert within an hour when a tracked company posts a new internship in Canada (set in `data/settings.json`), at no cost.

**Status:** Built and pushed. Waiting on GitHub secrets, cron-job.org, and Healthchecks.io before scheduled runs start.

## Architecture

| Part | Where | Role |
|---|---|---|
| `scripts/scraper.py` | GitHub Actions | Reads `data/companies.json` and runs each company's method |
| `scripts/methods/` | GitHub Actions | One file per scraping method |
| `scripts/filters.py` | GitHub Actions | Internship keywords and allowed countries |
| `scripts/alerts.py` | GitHub Actions | Telegram right away, Gmail at 8am and 5pm |
| `scripts/add_company.py` | Your PC only | Adds companies from plain text, using Claude when needed |
| `scripts/pipeline/` | Your PC only | Discover, probe, detect, validate, investigate |
| `data/` | Repo | Settings, prompts, method catalog, companies, seen jobs |
| `data/tmp/` | Your PC only | Files Python and Claude use to pass data |

No AI runs in GitHub Actions. Claude only helps add companies, and only the validator can approve one.

## Data files

| File | Contents |
|---|---|
| `data/settings.json` | Countries, internship keywords, email times, limits |
| `data/methods.json` | Every scraping method and its parameters |
| `data/prompts.json` | Every Claude prompt, its tools, and its output file |
| `data/companies.json` | Verified companies with method, parameters, and verification counts |
| `data/companies_entered.json` | Everything you entered, with its status and reason |
| `data/seen_jobs.json` | Jobs already found, alert queues, and failure counts |
| `data/tmp/recommendations.json` | Claude's suggested scraper changes, kept permanently |

## Schedule

- cron-job.org starts runs every 20 minutes from 8am to 4:40pm, then at 5pm and 8pm Eastern.
- Telegram alerts go out on the run that finds a job.
- Emails go out at 8am and 5pm to you and `FRIEND_EMAIL`.
- Healthchecks.io emails you if successful runs stop.

## Open items

- [ ] Add the GitHub secrets and start the first run.
- [ ] Set up cron-job.org and Healthchecks.io.
- [ ] Check real run time against the private repo's Actions minutes.
- [ ] Review `data/tmp/recommendations.json` and add the methods it suggests.
