# Internship Scraper Plan

## Timing requirements (Eastern time)

| What | When | Notes |
|---|---|---|
| Scrape run | Weekdays: 8:00am, every hour 10am to 4pm, 8:00pm | 9 runs a day, started by cron-job.org. No scraping on weekends. |
| Weekend reminder | Saturday and Sunday, 8:00am | Telegram only: a reminder to apply, with the number of open internships. No scraping, about 10 seconds. |
| Email runs | Weekdays, 8:30am and 4:30pm | Also scrape runs. Without them, the 8:30 email waits for the 10am run and the 4:30 email for the 8pm run. |
| Telegram alert | On the run that finds a new job | Within an hour in the daytime |
| Email update | Weekdays, 8:30am and 4:30pm (`email_times`) | Sent on the first run at or after that time. A failed one is retried on the next run. Monday 8:30am covers everything since Friday 4:30pm. |
| Daily status message | First run of the day (8:00am) | "X/Y companies OK" |
| Active-job check | Every run, at no extra cost | Each run already reads every company's full listing. A stored job missing from more than 3 successful runs in a row (`forget_after_missed_runs`) is removed. Failed or empty runs don't count. |
| Failure alert | After 3 failed runs in a row | About 3 hours in the daytime |
| Run time limit | 10 minutes per run (`timeout-minutes`) | A safety cap, not reserved compute. A run takes about 3 minutes. Raise it as companies grow. |
| Healthchecks.io | Pinged by every successful scrape run | Cron schedule `0 8,10-16,20 * * 1-5`, so nights and weekends aren't alerts |
| Adding companies | On demand, on your PC | Claude gets up to 5 attempts or 10 minutes per company |

**cron-job.org:** Monday to Friday, one job at minute 0, hours 8, 10–16, and 20, and one at minute 30, hours 8 and 16. Saturday and Sunday, one job at 8:00 with the body `{"ref":"main","inputs":{"reminder":"true"}}`.

**Actions minutes:** about 22 weekdays × 11 runs × 2 billed minutes, plus 8 one-minute reminders ≈ 500 of the 3,000 free minutes a month.

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
| `data/seen_jobs.json` | Currently active matching jobs per company (title, location, first and last seen), alert queues, and failure counts |
| `data/tmp/recommendations.json` | Claude's suggested scraper changes, kept permanently |
| `sample/` | Approved alert examples: `email.pdf`, `email.html`, `email.txt`, `telegram.txt`. `tests/test_alert_format.py` fails if alerts stop matching them. To change the format, edit `scripts/alerts.py`, run `scripts/make_samples.py`, and commit. |

## Open items

- [ ] Add the GitHub secrets and start the first run.
- [ ] Set up cron-job.org and Healthchecks.io.
- [ ] Check real run time against the private repo's Actions minutes.
- [ ] Review `data/tmp/recommendations.json` and add the methods it suggests.
