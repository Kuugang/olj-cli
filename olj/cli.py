import argparse
import json
import logging
import os
import time
from typing import cast
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from curl_cffi import requests

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

AUTHENTICATE_URL = "https://www.onlinejobs.ph/authenticate"
LOGIN_URL = "https://www.onlinejobs.ph/login"
JOBS_URL = "https://www.onlinejobs.ph/jobseekers/jobsearch"
APPLY_URL = "https://www.onlinejobs.ph/apply"

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://www.onlinejobs.ph",
    "priority": "u=0, i",
    "referer": "https://www.onlinejobs.ph/login",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def make_session(cookies: dict | None = None) -> requests.Session:
    session = requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)
    if cookies:
        session.cookies.update(cookies)
    return session


def get_input_value(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("input", {"name": name})
    if tag is None:
        logger.warning(f"Input field '{name}' not found")
        return None
    return cast(str, tag.get("value"))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def login(email: str, password: str) -> dict | None:
    """Login and print cookies as JSON."""

    def login_failed(html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        error_tag = soup.find("p", class_="error")
        if (
            error_tag
            and "email address or password is incorrect"
            in error_tag.get_text(strip=True).lower()
        ):
            return True
        return False

    session = make_session()

    logger.info("Fetching CSRF token from login page...")
    resp = session.get(LOGIN_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    csrf_token = get_input_value(soup, "csrf-token")

    if not csrf_token:
        logger.error("No CSRF token found. Exiting...")
        raise SystemExit(1)

    logger.info(f"Logging in as {email}...")
    resp = session.post(
        AUTHENTICATE_URL,
        data={
            "csrf_token": csrf_token,
            "info[email]": email,
            "info[password]": password,
            "login": "Login →",
        },
    )
    if login_failed(resp.text):
        logger.error("Login failed: invalid email or password!")
        return None

    logger.info("Login successful")

    cookies = dict(session.cookies)
    print(json.dumps(cookies))
    return cookies


def apply(
    cookies: dict,
    job_url: str,
    subject: str,
    message: str,
    contact_info: str,
    apply_points: int = 1,
) -> None:
    """Apply to a job using saved cookies."""

    def is_already_applied(soup: BeautifulSoup) -> bool:
        button = soup.find(
            "button",
            class_="btn btn-danger btn-rounded btn-addpad fs-16",
            disabled=True,
        )
        if button and "applied" in button.get_text(strip=True).lower():
            return True
        return False

    session = make_session(cookies)

    # Step 1: Job page → contact_email, job_id, back_id
    logger.info(f"Fetching job page: {job_url}")
    resp = session.get(job_url)

    soup = BeautifulSoup(resp.text, "html.parser")
    if is_already_applied(soup):
        logger.error("You have already applied to this job!")
        return

    csrf_token = get_input_value(soup, "csrf-token")
    contact_email = get_input_value(soup, "contact_email")
    job_id = get_input_value(soup, "job_id")
    back_id = get_input_value(soup, "back_id")

    logger.debug(f"{csrf_token=} {contact_email=} {job_id=} {back_id=}")

    # Step 2: POST to /apply → get the actual apply form
    logger.info("Fetching apply form...")
    apply_resp = session.post(
        APPLY_URL,
        data={
            "csrf_token": csrf_token,
            "contact_email": contact_email,
            "job_id": job_id,
            "back_id": back_id,
        },
    )
    apply_soup = BeautifulSoup(apply_resp.text, "html.parser")

    # Step 3: Parse apply form fields
    csrf_token = get_input_value(apply_soup, "csrf-token")
    info_name = get_input_value(apply_soup, "info[name]")
    info_email = get_input_value(apply_soup, "info[email]")
    sent_to_e_id = get_input_value(apply_soup, "sent_to_e_id")
    email_sent_count_today = get_input_value(apply_soup, "email_sent_count_today")

    logger.debug(
        f"{info_name=} {info_email=} {sent_to_e_id=} {email_sent_count_today=}"
    )

    # Step 4: Submit
    data = {
        "csrf-token": csrf_token,
        "info[name]": info_name,
        "info[email]": info_email,
        "info[subject]": subject,
        "info[message]": message,
        "points": apply_points,
        "op": "Send Email",
        "contact_email": contact_email,
        "email_sent_count_today": email_sent_count_today,
        "back_id": back_id,
        "sent_to_e_id": sent_to_e_id,
        "job_id": job_id,
        "contact_info": contact_info,
    }

    logger.info(f"Submitting application for job {job_id}...")
    logger.debug(f"Payload: {data}")
    session.post(APPLY_URL, data=data)
    logger.info(f"Successfully applied to job_id {job_id}")


def jobs(
    search_filter: str | None = None,
    pages: int | None = None,
) -> list[dict] | None:
    """Scrape jobs and print as JSON."""
    session = make_session()

    def get_jobs_url(page: int, params: dict | None = None) -> str:
        url = JOBS_URL if page == 1 else f"{JOBS_URL}/{(page - 1) * 30}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def parse_jobs(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        all_jobs: list[dict] = []
        cards = soup.find_all("div", class_="jobpost-cat-box")
        logger.debug(f"Found {len(cards)} job cards in HTML")

        for card in cards:
            link_tag = card.find("a", href=True)
            url = f"https://www.onlinejobs.ph{link_tag['href']}" if link_tag else ""

            title_tag = card.find("h4")
            title = ""
            if title_tag:
                badge = title_tag.find("span")
                if badge:
                    badge.extract()
                title = title_tag.get_text(strip=True)

            posted_by, posted_on = "", ""
            meta_p = card.find("p", class_="fs-13")
            if meta_p:
                text = meta_p.get_text(strip=True)
                if "•" in text:
                    parts = text.split("•")
                    posted_by = parts[0].strip()
                    posted_on = parts[1].replace("Posted on", "").strip()

            rate_dd = card.find("dd")
            rate = rate_dd.get_text(strip=True) if rate_dd else ""

            all_jobs.append(
                {
                    "url": url,
                    "title": title,
                    "posted_by": posted_by,
                    "posted_on": posted_on,
                    "rate": rate,
                }
            )

        return all_jobs

    def enrich(job_list: list[dict]) -> list[dict]:
        for i, job in enumerate(job_list, 1):
            url = job.get("url")
            if not url:
                logger.warning(f"Job #{i} has no URL, skipping description fetch")
                job["description"] = ""
                continue
            logger.debug(
                f"Fetching description for job #{i}: {job.get('title', 'N/A')}"
            )
            resp = session.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_tag = soup.find("p", id="job-description")
            job["description"] = desc_tag.get_text(strip=True) if desc_tag else ""
            if not desc_tag:
                logger.warning(f"No description found for job #{i}: {url}")
            time.sleep(0.5)
        return job_list

    def fetch_page(page: int) -> list[dict]:
        params = {
            "jobkeyword": search_filter or "",
            "skill_tags": "",
            "gig": "on",
            "partTime": "on",
            "fullTime": "on",
            "isFromJobsearchForm": "1",
        }
        url = get_jobs_url(page, params)
        logger.info(f"Fetching jobs page {page}: {url}")
        resp = session.get(url)
        job_list = parse_jobs(resp.text)
        logger.info(
            f"Page {page}: parsed {len(job_list)} jobs, enriching with descriptions..."
        )
        return enrich(job_list)

    all_jobs: list[dict] = []

    if pages:
        for page in range(1, pages + 1):
            all_jobs.extend(fetch_page(page))
            logger.info(f"Total jobs collected so far: {len(all_jobs)}")
    else:
        logger.info("No page limit — scraping until no jobs found")
        page = 1
        while True:
            page_jobs = fetch_page(page)
            if not page_jobs:
                logger.info(f"No jobs found on page {page}. Stopping.")
                break
            all_jobs.extend(page_jobs)
            logger.info(f"Total jobs collected so far: {len(all_jobs)}")
            page += 1

    logger.info(f"Scraping complete. Total jobs: {len(all_jobs)}")
    print(json.dumps(all_jobs, indent=2))
    return all_jobs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OnlineJobs.ph CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    sub = parser.add_subparsers(dest="command", required=True)

    # -- login --
    login_p = sub.add_parser("login", help="Login and output cookies as JSON")
    login_p.add_argument(
        "--email", required=True, help="Account email (or set OLJ_EMAIL)"
    )
    login_p.add_argument(
        "--password", required=True, help="Account password (or set OLJ_PASSWORD)"
    )

    # -- apply --
    apply_p = sub.add_parser("apply", help="Apply to a job posting")
    apply_p.add_argument(
        "--cookies", required=True, help="JSON cookies string from `login`"
    )
    apply_p.add_argument("--job-url", required=True, help="Full URL of the job posting")
    apply_p.add_argument("--subject", required=True, help="Email subject")
    apply_p.add_argument("--message", required=True, help="Email message body")
    apply_p.add_argument(
        "--contact-info", required=True, help="Contact info to include"
    )
    apply_p.add_argument(
        "--apply-points", type=int, default=1, help="Points to spend (default: 1)"
    )

    # -- jobs --
    jobs_p = sub.add_parser("jobs", help="Search and scrape job listings")
    jobs_p.add_argument("--filter", dest="search_filter", help="Keyword filter")
    jobs_p.add_argument("--pages", type=int, help="Number of pages to scrape")

    return parser.parse_args()


def main() -> list | dict | None:
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    if args.command == "login":
        email = args.email or os.environ.get("OLJ_EMAIL", "")
        password = args.password or os.environ.get("OLJ_PASSWORD", "")
        if not email or not password:
            logger.error(
                "--email and --password are required (or set OLJ_EMAIL / OLJ_PASSWORD)"
            )
            raise SystemExit(1)
        return login(email, password)

    elif args.command == "apply":
        apply(
            cookies=json.loads(args.cookies),
            job_url=args.job_url,
            subject=args.subject,
            message=args.message,
            contact_info=args.contact_info,
            apply_points=args.apply_points,
        )

    elif args.command == "jobs":
        return jobs(
            search_filter=args.search_filter,
            pages=args.pages,
        )


if __name__ == "__main__":
    main()
