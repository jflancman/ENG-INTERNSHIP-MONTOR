"""
Internship watcher - Summer 2027 engineering internships in Canada and the US.

Sources:
  1. SimplifyJobs/Summer2027-Internships - community-maintained feed covering
     thousands of companies, updated daily (github.com/SimplifyJobs/Summer2027-Internships)
  (NVIDIA's own site is watched separately by nvidia_watch.py)

Remembers what it has already seen and emails you (via Gmail) one digest of
anything new, hardware roles first.

Setup:
  pip install requests
  Environment variables (GitHub secrets):
    GMAIL_ADDRESS       your Gmail address
    GMAIL_APP_PASSWORD  a 16-character Gmail app password
"""

import json
import os
import pathlib
import re
import smtplib
from email.message import EmailMessage

import requests

# ----------------------------------------------------------------------------
# Settings - edit these to change what counts as a match
# ----------------------------------------------------------------------------

TERMS = ["Summer 2027"]  # add "Fall 2027" etc. if you want other terms

# Simplify categories to keep (Quant and Product are left out)
CATEGORIES = {
    "Hardware",
    "Software",
    "Software Engineering",
    "AI/ML/Data",
    "Data Science, AI & Machine Learning",
}

# Skip titles that are clearly for grad students
EXCLUDE_TITLE = re.compile(r"\b(phd|ph\.d|mba|master'?s)\b", re.IGNORECASE)

# Skip US roles that require US citizenship
EXCLUDE_US_CITIZEN_ONLY = True

# Order of sections in the email
CATEGORY_ORDER = ["Hardware", "Software", "AI/ML/Data"]

# ----------------------------------------------------------------------------

SIMPLIFY_URL = ("https://raw.githubusercontent.com/SimplifyJobs/"
                "Summer2027-Internships/dev/.github/scripts/listings.json")
NVIDIA_API = "https://jobs.nvidia.com/api/pcsx/search"
NVIDIA_SITE = "https://jobs.nvidia.com"
NVIDIA_KEYWORDS = ["software", "hardware", "systems", "computer", "architecture",
                   "firmware", "embedded", "gpu", "cuda", "asic", "verification",
                   "dft", "design", "engineer", "deep learning", "ai"]

STATE_FILE = pathlib.Path(__file__).with_name("seen_internships.json")  # separate from nvidia_watch.py
HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
}
INTERN_RE = re.compile(r"\bintern(ship)?s?\b", re.IGNORECASE)

US_PLACES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming",
    "United States", "USA", "Remote in USA", "NYC", "SF", "LA", "South SF", "DC",
}


def in_us_or_canada(loc):
    """True for e.g. 'Austin, TX', 'Toronto, ON, Canada', 'NYC', 'Remote in USA'."""
    loc = loc.strip()
    return ("canada" in loc.lower()
            or loc in US_PLACES
            or re.search(r", [A-Z]{2}$", loc) is not None)   # US city, ST


def get_json(url, **kwargs):
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, **kwargs)
    except requests.RequestException as e:
        raise RuntimeError(f"could not reach {url}: {e!r}")
    if r.status_code != 200:
        raise RuntimeError(f"{url} returned HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


# ---------------------------- sources ---------------------------------------

def simplify_jobs():
    jobs = []
    for x in get_json(SIMPLIFY_URL):
        if not x.get("active") or x.get("is_visible") is False:
            continue
        if not any(t in x.get("terms", []) for t in TERMS):
            continue
        if x.get("category") not in CATEGORIES:
            continue
        locs = [l for l in x.get("locations", []) if in_us_or_canada(l)]
        if not locs:
            continue
        degrees = x.get("degrees") or []
        if degrees and "Bachelor's" not in degrees:
            continue
        if EXCLUDE_TITLE.search(x.get("title", "")):
            continue
        if EXCLUDE_US_CITIZEN_ONLY and x.get("sponsorship") == "U.S. Citizenship is Required":
            continue
        cat = x["category"]
        if cat == "Software Engineering":
            cat = "Software"
        elif cat.startswith("Data Science"):
            cat = "AI/ML/Data"
        jobs.append({
            "key": f"simplify:{x['id']}",
            "company": x.get("company_name", "?"),
            "title": x.get("title", "?"),
            "locations": locs,
            "url": x.get("url", ""),
            "category": cat,
        })
    return jobs


def nvidia_jobs():
    raw, start = [], 0
    while True:
        data = get_json(NVIDIA_API, params={"domain": "nvidia.com", "query": "intern",
                                            "location": "", "start": start}).get("data") or {}
        page = data.get("positions") or []
        raw += page
        start += len(page)
        if not page or start >= data.get("count", 0) or start > 1000:
            break

    jobs = []
    for p in raw:
        title = p.get("name", "")
        if not (INTERN_RE.search(title) or p.get("department") == "Intern"):
            continue
        if EXCLUDE_TITLE.search(title):
            continue
        if not any(k in title.lower() for k in NVIDIA_KEYWORDS):
            continue
        locs = [l for l in p.get("locations") or []
                if re.match(r"(US|Canada|Remote - US|Remote - Canada)\b", l)]
        if not locs:
            continue
        hw = re.search(r"verification|asic|vlsi|hardware|circuit|dft|architecture|"
                       r"design|mixed signal|physical", title, re.IGNORECASE)
        jobs.append({
            "key": f"nvidia:{p['id']}",
            "company": "NVIDIA",
            "title": f"{title} [{p.get('displayJobId', '')}]",
            "locations": locs,
            "url": NVIDIA_SITE + p.get("positionUrl", f"/careers/job/{p['id']}"),
            "category": "Hardware" if hw else "Software",
        })
    return jobs


# NVIDIA is tracked separately by nvidia_watch.py; add "nvidia": nvidia_jobs here to fold it in.
SOURCES = {"simplify": simplify_jobs}

# ---------------------------- state & email ---------------------------------

def load_state():
    if not STATE_FILE.exists():
        return set(), set()
    data = json.loads(STATE_FILE.read_text())
    if isinstance(data, list):                      # old NVIDIA-only format
        return {f"nvidia:{i}" for i in data}, {"nvidia"}
    return set(data.get("seen", [])), set(data.get("sources", []))


def save_state(seen, sources):
    STATE_FILE.write_text(json.dumps({"sources": sorted(sources), "seen": sorted(seen)}))


def send_email(new_jobs):
    address = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    # drop duplicates of the same posting listed by both sources
    unique, dupes = [], set()
    for j in new_jobs:
        k = (j["company"].lower(), re.sub(r"\s*\[.*?\]$", "", j["title"]).lower())
        if k not in dupes:
            dupes.add(k)
            unique.append(j)

    sections = []
    for cat in CATEGORY_ORDER + sorted({j["category"] for j in unique} - set(CATEGORY_ORDER)):
        group = sorted((j for j in unique if j["category"] == cat), key=lambda j: j["company"])
        if not group:
            continue
        lines = [f"- {j['company']}: {j['title']}\n  {', '.join(j['locations'])}\n  {j['url']}"
                 for j in group]
        sections.append(f"== {cat} ({len(group)}) ==\n\n" + "\n\n".join(lines))

    n_hw = sum(j["category"] == "Hardware" for j in unique)
    msg = EmailMessage()
    msg["Subject"] = f"{len(unique)} new internship(s)" + (f" - {n_hw} hardware" if n_hw else "")
    msg["From"] = address
    msg["To"] = address
    msg.set_content("\n\n\n".join(sections))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(address, password)
        smtp.send_message(msg)


def main():
    seen, known_sources = load_state()
    new_jobs, errors = [], []

    for name, fetch in SOURCES.items():
        try:
            jobs = fetch()
        except Exception as e:                     # one broken source shouldn't stop the rest
            errors.append(f"{name}: {e}")
            continue
        fresh = [j for j in jobs if j["key"] not in seen]
        if name in known_sources:
            new_jobs += fresh
        print(f"{name}: {len(jobs)} matching, {len(fresh)} new"
              + ("" if name in known_sources else " (first run for this source, baseline saved)"))
        seen |= {j["key"] for j in jobs}
        known_sources.add(name)

    if new_jobs:
        send_email(new_jobs)
    save_state(seen, known_sources)

    for e in errors:
        print("ERROR", e)
    if errors and len(errors) == len(SOURCES):
        raise SystemExit("All sources failed")


if __name__ == "__main__":
    main()
