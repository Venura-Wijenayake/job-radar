# Job Market Intelligence Platform (job-radar)

> Daily ETL pipeline + SQL analytics + interactive dashboard for job market intelligence. Live demo personalized via uploaded resume.

**Status:** in development

## Overview

job-radar is built on a "generic underneath, personal on top" architecture: the core engine — scrapers, storage, scoring, and dashboard — operates on any structured job-data source and is fully source-agnostic. Personalization is layered on top by parsing an uploaded resume into a skill profile that drives match scoring and dashboard views. The same codebase is therefore intended to serve double duty: as the author's personal job-discovery tool, and as a productized template that can be repurposed for Fiverr/Upwork clients with no engine changes — only resume input and source configuration.

## Tech Stack

- **Language:** Python 3.11+
- **Storage:** SQLite via SQLAlchemy
- **Scraping / ingest:** httpx, BeautifulSoup4, feedparser
- **Resume parsing:** pdfplumber, python-docx
- **Analytics / dashboard:** pandas, plotly, Streamlit
- **Testing:** pytest
- **Config / env:** PyYAML, python-dotenv
- **Deployment:** Streamlit Cloud (dashboard) + GitHub Actions (cron-driven scraping)

## Setup

_TBD_

## Usage

_TBD_

## Architecture

_TBD_

## Roadmap

_TBD_
