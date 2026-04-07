# OnlineJobs.ph CLI

A command-line tool to automate job applications and scraping on [OnlineJobs.ph](https://www.onlinejobs.ph).

## Features

- **Login**: Authenticate with OnlineJobs.ph and export session cookies
- **Apply**: Automatically apply to job postings with custom messages and contact info
- **Jobs**: Search and scrape job listings with descriptions

## Installation

### Requirements

- Python 3.8+
- Dependencies: `requests`, `beautifulsoup4`, `curl-cffi`

### Setup

```bash
pip install -r requirements.txt
```

## Example Usage

### 1. Login — Get Session Cookies

Authenticate and save your session cookies for use in other commands.

```bash
COOKIES=$(python main.py login --email you@example.com --password secret)
```

This prints the cookies as JSON to stdout, which you can store in the `COOKIES` variable.

### 2. Apply to a Job

Submit an application to a specific job posting.

```bash
python main.py apply \
  --cookies "$COOKIES" \
  --job-url "https://www.onlinejobs.ph/jobseekers/job/12345" \
  --subject "Applying for Part time developer" \
  --message "I would like to apply, thank you." \
  --contact-info "Email: you@example.com | GitHub: yourhandle"
```

**Parameters:**

- `--cookies`: JSON cookies string from the `login` command
- `--job-url`: Full URL of the job posting
- `--subject`: Email subject line
- `--message`: Email message body
- `--contact-info`: Your contact information
- `--apply-points` (optional): Points to spend (default: 1)

### 3. Scrape Jobs

Search and scrape job listings with full descriptions.

```bash
python main.py jobs --filter "python developer" --pages 3
```

**Parameters:**

- `--filter` (optional): Keyword filter for search
- `--pages` (optional): Number of pages to scrape (if not specified, scrapes until no jobs found)

**Output:** JSON array of jobs with `url`, `title`, `posted_by`, `posted_on`, `rate`, and `description`

## Commands

### `login`

Authenticate with OnlineJobs.ph and output session cookies as JSON.

```bash
python main.py login --email <email> --password <password>
```

**Environment Variables:**

- `OLJ_EMAIL`: Account email (alternative to `--email`)
- `OLJ_PASSWORD`: Account password (alternative to `--password`)

### `apply`

Apply to a job posting using authenticated session.

```bash
python main.py apply --cookies <JSON> --job-url <url> --subject <subject> --message <message> --contact-info <info>
```

### `jobs`

Search and scrape job listings.

```bash
python main.py jobs [--filter <keyword>] [--pages <number>]
```

## Debug

Enable debug logging for any command:

```bash
python main.py --debug jobs --filter "react"
```

## Example Workflow

```bash
# 1. Search for jobs (no authentication needed)
python main.py jobs --filter "python developer" --pages 3

# 2. Login to get cookies (if you want to apply)
COOKIES=$(python main.py login --email you@example.com --password secret)

# 3. Apply to a specific job
python main.py apply \
  --cookies "$COOKIES" \
  --job-url "https://www.onlinejobs.ph/jobseekers/job/1604447" \
  --subject "Applying for Senior Magento 2 Developer" \
  --message "I would like to apply, thank you." \
  --contact-info "Email: you@example.com | GitHub: yourhandle"
```

## How It Works

### Login Flow

1. Fetches the login page to extract CSRF token
2. Submits credentials to authenticate endpoint
3. Stores session cookies for subsequent requests

### Apply Flow

1. Fetches the job posting page
2. Extracts CSRF token, job ID, and other metadata
3. Fetches the application form
4. Submits the application with subject, message, and contact info

### Jobs Scraping

1. Fetches job listing pages with optional keyword filter
2. Parses job cards to extract title, URL, poster, and date
3. Fetches each job's detail page to extract full description
4. Returns complete job data as JSON
