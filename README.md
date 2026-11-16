# Engineering Internship Monitor

Automatically tracks new **Summer 2027 engineering internships in the US and Canada** and
emails me a digest whenever new postings appear. Runs every 2 hours on GitHub Actions, so
no computer needs to stay on.

## How it works

1. **Fetch:** pulls the [SimplifyJobs Summer 2027 internship list](https://github.com/SimplifyJobs/Summer2027-Internships),
   a community-maintained feed of 17,000+ postings from thousands of companies.
2. **Filter:** keeps only postings that match:
   - Term: Summer 2027
   - Category: hardware, software or AI/ML (quant and product roles are skipped)
   - Location: United States or Canada
   - Level: open to bachelor's students (PhD and MBA roles are dropped)
3. **Compare:** checks each match against `seen_internships.json`, the list of postings it
   has already seen, so only new ones are reported.
4. **Notify:** sends one email listing every new posting, grouped by category with hardware
   first, including the company, role, location and application link.
5. **Save:** commits the updated `seen_internships.json` back to the repo for the next run.

On the very first run it records every current posting without emailing, so it doesn't
send hundreds at once.

## Project structure

| File | Purpose |
| --- | --- |
| `internship_watch.py` | Fetches, filters and compares postings, and sends the email |
| `.github/workflows/watch.yml` | Runs the script every 2 hours and saves its state |
| `seen_internships.json` | Postings already seen (created and updated automatically) |

## Setup

1. Fork or copy this repo.
2. Create a [Gmail app password](https://myaccount.google.com/apppasswords) (requires
   2-Step Verification).
3. In the repo, go to **Settings → Secrets and variables → Actions** and add:
   - `GMAIL_ADDRESS`: the Gmail address to send from and to
   - `GMAIL_APP_PASSWORD`: the 16-character app password
4. Go to **Actions → Internship watcher → Run workflow** to run it once and save the baseline.

Credentials are stored only as encrypted GitHub secrets and are never written to the code
or the logs.

## Customizing

All filters are settings at the top of `internship_watch.py`:

| Setting | What it controls |
| --- | --- |
| `TERMS` | Which internship terms to include, e.g. add `"Fall 2027"` |
| `CATEGORIES` | Which role categories to keep |
| `EXCLUDE_TITLE` | Title keywords to skip (PhD, MBA, Master's) |
| `EXCLUDE_US_CITIZEN_ONLY` | Skip US roles that require US citizenship |

To change how often it runs, edit the `cron` line in `.github/workflows/watch.yml`.

## Built with

Python (`requests`, `smtplib`), GitHub Actions, Gmail SMTP
