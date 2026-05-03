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

```bash
# Clone, create venv, install deps
python -m venv venv
venv\Scripts\activate                  # Windows
# source venv/bin/activate              # macOS/Linux
pip install -r requirements.txt

# Copy env template
cp .env.example .env
```

## Running the Dashboard

First-time setup (after Phase 1+2 are in place):

```bash
# 1. Initialize the SQLite schema and seed default sources
python scripts/init_db.py

# 2. Parse your resume into a profile (PDF or DOCX)
python scripts/parse_resume.py data/resumes/your_resume.pdf your_profile_name

# 3. Scrape job listings
python scripts/run_scraper.py remoteok

# 4. Score every item against your profile
python scripts/score_items.py your_profile_name --force

# 5. (Optional) Pre-extract per-item keywords for the resume-tailor feature
python scripts/extract_keywords.py --force

# 6. Launch the dashboard
streamlit run dashboard/app.py
```

The dashboard opens at <http://localhost:8501>. The sidebar carries a profile selector, refresh button, and live stats. The two tabs are:

### 📋 Today's Queue

![Today's Queue](docs/screenshots/today_queue.png)

Sorted job feed (highest score first). Filters at the top: minimum score, source, and a title/company substring search. Each card shows a color-coded score badge, title (linked to the original posting), company • location • posted date • source, the top 3 matched terms as gray pills, and four single-click status buttons:

- **Interested** — adds it to your pipeline
- **Applied** — adds to pipeline and stamps the application date
- **Skip** — hides it from the queue (stays in the DB)
- **Hide** — same as skip (separate status for "rejected on sight" vs "saved for later")

### 📊 Pipeline

![Pipeline](docs/screenshots/pipeline.png)

Kanban view of your tracked applications across seven stages: Interested → Applied → Phone Screen → Interview → Offer → Rejected → Ghosted. Each card has an Edit expander where you can update notes and move it to a different stage; Save persists immediately.

### ✂️ Resume Tailor

![Resume Tailor](docs/screenshots/resume_tailor.png)

Pick a top-20 scored item to see how your resume matches its JD keywords. Three columns surface:

- **✅ Strong matches** — JD keywords mentioned ≥ 2× in your resume
- **⚠️ Buried in resume** — listed once but worth amplifying
- **❌ Missing skills** — top JD keywords absent from your resume

The Suggested rewrites expander gives template bullet phrasings for each buried/missing term, sourced from a built-in dictionary of ~33 common skills (Tableau, Snowflake, Airflow, dbt, A/B testing, regression, etc.).

### 📈 Market Insights

![Market Insights](docs/screenshots/market_insights.png)

Four Plotly charts on the full corpus:

- Top hiring companies (horizontal bar, top 15)
- Skill demand frequency from the keyword extracts (horizontal bar, top 20)
- Posting velocity per day (line, last 30 days)
- Source breakdown (pie)

Plus three metric tiles up top: total items, companies hiring, freshest posting date.

### ⚙️ Settings

![Settings](docs/screenshots/settings.png)

Three sections:

1. **Profile** — read-only view of profile metadata, criteria-by-kind counts, and filter config.
2. **Manual criteria** — add/remove `source="manual"` criteria via a form. Adding or removing triggers an immediate force re-score with a spinner.
3. **Skills taxonomy** — read-only JSON view of `config/skills_taxonomy.yaml` so you can see what's being matched against without leaving the app.

## Architecture

```
job-radar/
├── scrapers/    # source-specific scrapers + base interface
├── db/          # SQLAlchemy models, session helpers, seed data
├── scoring/     # text utilities, resume parser, scorer, JD keyword extractor, batch runners
├── dashboard/   # Streamlit app + data-access layer
├── config/      # YAML taxonomies (skills_taxonomy.yaml)
├── tests/       # pytest suite (82 tests as of Phase 3a)
├── scripts/     # CLI entry points and migrations
├── data/        # SQLite database (gitignored) + resume uploads
└── .github/workflows/  # GitHub Actions cron (Phase 4)
```

The engine is fully source-agnostic; tables use generic names (`items`, `sources`, `criteria`) so the same schema can later support lead-gen, real estate, or any structured-data scoring use case. `profile_id` foreign keys exist everywhere for future multi-profile support.

## Roadmap

- **Phase 0** — project scaffolding ✅
- **Phase 1** — schema, RemoteOK scraper, resume parser, dedup ✅
- **Phase 2** — scoring engine + JD keyword extraction ✅
- **Phase 2.5** — dataset-relative score normalization ✅
- **Phase 3a** — Streamlit dashboard MVP (Today's Queue + Pipeline) ✅
- **Phase 3.5** — Source expansion (4 scrapers) + anti-keyword calibration ✅
- **Phase 3.6** — Geographic + language filtering ✅
- **Phase 3.7** — Recency filter, analytics keyword recategorization, manager penalty ✅
- **Phase 3b** — Resume Tailor + Market Insights + Settings tabs ✅
- **Phase 3.8** — Adzuna scraper (5th source, ~1,800 new items) + citizenship/license/ghost filters ✅
- **Phase 4** — GitHub Actions cron + Streamlit Cloud deploy + screenshots in this README
