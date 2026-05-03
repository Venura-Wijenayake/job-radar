# Phase 4 Plan — CI cron + Streamlit Cloud deploy + screenshots

Phase 4 has three sub-tasks with very different blast radii. This doc lays out
my proposed approach, the architectural decisions you need to call, and the
commit shape — so the live execution is mechanical.

---

## Sub-task 4.1 — GitHub Actions cron

### Goal

A daily workflow that scrapes all sources, scores against
`venura_data_analyst`, and commits an updated, public-safe DB back to the
repo so Streamlit Cloud can pick it up on its next auto-redeploy.

### The architecture decision: where does the DB live?

Five real options, none free of trade-offs:

| Option | Pros | Cons |
|---|---|---|
| **A. Commit DB to repo** | Simplest. Streamlit Cloud auto-redeploys on push. Single source of truth. | Binary diffs balloon git history. Anyone with repo read can see all your tracking data. |
| **B. Commit a stripped public-safe DB; keep personal DB local** | Public sees jobs+scores; private tracking stays on your machine. Clean privacy boundary. | Two DBs to reason about. Local dev needs a clear "import latest public snapshot" step. |
| **C. External Postgres (Supabase free tier)** | Both cron and Cloud read/write the same live DB. Tracking syncs across devices. | Adds an account/dependency. Migration from SQLite needed. Free tier has limits. |
| **D. GitHub Release artifact** | DB is downloadable, not in git history. | Streamlit Cloud can't auto-fetch artifacts on redeploy without custom bootstrap. |
| **E. Skip Cloud sync for now** | Cron just runs scrapers and uploads JSON snapshots; Cloud uses its own DB. | Cloud demo data goes stale unless we manually reseed. |

**My recommendation: B (stripped public-safe DB).**

Concretely: `data/job_radar.db` stays gitignored and local. The cron creates
`data/public_snapshot.db` containing only `sources`, `items`, `scores`,
`keyword_extracts` — no `profiles`, no `criteria`, no `tracking`, no
`applications`. It commits that file. Streamlit Cloud reads
`data/public_snapshot.db`. Personal tracking is invisible to the public
demo and still lives in your local DB for the real workflow.

This is a one-time architectural call. If you'd rather pick A, C, D, or E,
say which and I'll adjust.

### What the workflow does

`.github/workflows/daily_scrape.yml`:

1. Trigger: `schedule: cron: '0 14 * * *'` (14:00 UTC ≈ 7am Pacific) plus
   `workflow_dispatch` so you can run it on demand from the Actions UI.
2. Steps:
   - Check out repo
   - Setup Python 3.13, install requirements
   - Initialize a fresh local DB from the committed `public_snapshot.db`
   - `python scripts/init_db.py` (idempotent)
   - `python scripts/run_scraper.py --all` (uses Adzuna keys from secrets)
   - `python scripts/score_items.py demo_profile --force` (see below — the
     workflow scores a public **demo profile**, not your personal profile)
   - `python scripts/extract_keywords.py --force`
   - Run a new `scripts/export_public_snapshot.py` that copies the
     scrape-result tables into a fresh `data/public_snapshot.db`
   - Commit `data/public_snapshot.db` if changed; push back to main
3. Notification: fail-loud (workflow status reflects in repo), no email/Slack
   for now.

### Demo profile

The cron needs a profile to score against. We don't want it scoring your
personal `venura_data_analyst` profile and committing those scores back —
that's leaky.

Plan: ship a `demo_profile` whose criteria are derived from a
public-friendly resume (or even just a hand-curated set of skills). The
workflow seeds `demo_profile` if missing and scores against it. Your
personal profile stays in the local DB and is never touched by the cron.

### Secrets

GitHub repo secrets needed:

- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`

The workflow exports them into the runner's env so `dotenv` picks them up.
No `.env` file checked in.

### Files added / changed

| Path | Action |
|---|---|
| `.github/workflows/daily_scrape.yml` | new |
| `scripts/export_public_snapshot.py` | new — copies select tables to a fresh SQLite file |
| `scripts/seed_demo_profile.py` | new — idempotent demo profile setup |
| `dashboard/data.py` (and others reading the DB) | new env var `JOB_RADAR_PUBLIC_MODE` toggles between local DB + tracking and public_snapshot.db read-only |
| `data/public_snapshot.db` | added to git, gitignore exception |
| `tests/test_export_public_snapshot.py` | new — copy logic + table-list correctness |

### Verification

- The workflow runs once on `workflow_dispatch` from the Actions UI before
  the schedule fires.
- Tests cover the export script's "what gets included / excluded" logic.
- Manual: confirm `public_snapshot.db` opens, has only the 4 expected
  tables, and is small (<10 MB for ~2k items).

### Risks

- **Repo size growth from binary commits**: 2,177 items in SQLite ≈ 2-5 MB.
  At one commit/day for a year that's ~1.5 GB of git history. Not great but
  tolerable for a portfolio repo. Mitigations: monthly squash, or migrate
  to Option C if it gets ugly.
- **Adzuna rate limits**: 10 search terms × 5 pages = 50 requests, well
  under their daily quota. Confirmed in Phase 3.8.
- **Stale items pile up**: the cron never deletes. Recency filter handles
  display. We could add a "delete items older than 90 days" cleanup step
  to the workflow if the DB grows unwieldy. Defer to Phase 5.

### Commit shape

1. `chore(scripts): demo-profile seeder + public-snapshot exporter`
2. `feat(ci): daily scrape workflow under .github/workflows/`
3. `feat(dashboard): public-snapshot read mode for cloud deploy`
4. `test(ci): coverage for snapshot export`

---

## Sub-task 4.2 — Streamlit Cloud deploy

### Goal

A live `https://job-radar-...streamlit.app` URL that re-renders Phase 3b's
five tabs against the daily-refreshed `public_snapshot.db`.

### Decisions you need to call

1. **Public vs auth-gated.** Free Streamlit Cloud supports both. Public
   shows up nicely in a portfolio. Auth-gated (Google login allowlist)
   keeps it personal. **My rec: public**, given the snapshot is already
   stripped of tracking data.

2. **Deploy from `main` directly, or a `demo` branch.** A `demo` branch
   means you can keep main moving without redeploying every commit.
   Slightly more git overhead. **My rec: deploy from main**, with the
   workflow's commits acting as the redeploy trigger.

3. **Custom domain or `*.streamlit.app` subdomain.** Subdomain is
   zero-config. Custom needs DNS + cert setup. **My rec: subdomain for
   v1.**

4. **Sidebar profile selector**. Currently the dropdown only shows
   profiles that exist in the DB. In public mode it should show a single
   `demo_profile` and lock — no need for a selector. **My rec: when
   `JOB_RADAR_PUBLIC_MODE` is set, hide the selector and show a banner
   ("Demo profile · refreshed daily by GitHub Actions").**

5. **Tabs that don't make sense in public mode**:
   - Pipeline — meaningless without tracking. Hide it.
   - Settings — let visitors view but block writes. Or hide.
   - Resume Tailor — works fine on demo profile's criteria, keep visible.
   - Today's Queue, Market Insights — keep visible.

   **My rec: hide Pipeline + Settings in public mode; keep the other
   three.**

### Files added / changed

| Path | Action |
|---|---|
| `dashboard/app.py` | conditional tab rendering on `JOB_RADAR_PUBLIC_MODE` env var |
| `.streamlit/config.toml` | theme + layout settings (committed) |
| `.streamlit/secrets.toml.example` | template for any future secrets (gitignored secrets.toml stays gitignored) |
| `requirements.txt` | already covers what's needed; sanity-check a fresh install on the runner |
| `README.md` | "Try the live demo" section with the URL |

### Verification

- Local: run `JOB_RADAR_PUBLIC_MODE=1 streamlit run dashboard/app.py` and
  confirm Pipeline/Settings hidden, banner shows, demo data loads from
  `public_snapshot.db`.
- Deployed: hit the live URL after first cron run, confirm 5-second
  cold-start, charts render, queue shows demo profile's matches.

### Risks (one-way-door)

- **Public URL with personal data**: mitigated by the snapshot
  stripping, but worth a final pass before pointing the deploy at it.
  Concrete check: I'll run the export locally and grep the output DB for
  any `tracking`/`applications`/`criteria` tables before committing.
- **Free-tier resource limits**: 1 GB RAM. 2,177 items + plotly should be
  fine; if charts OOM we move to a sampled view or upgrade.
- **Commit-rate spam from cron**: every day produces a commit even if no
  items changed. Mitigations: skip the commit when the snapshot is
  byte-identical to the last one (`git diff --quiet` check before push).

### Commit shape

1. `feat(dashboard): JOB_RADAR_PUBLIC_MODE conditional rendering`
2. `chore(streamlit): config.toml + secrets.toml.example`
3. `docs(readme): live demo URL`

The actual "click the button on Streamlit Cloud to deploy" step is
manual on your side — I can't connect a Streamlit Cloud account from
here. I'll list the exact 4 clicks needed.

---

## Sub-task 4.3 — Screenshots in README

### Goal

Five PNGs in `docs/screenshots/`, referenced by README:

- `today_queue.png`
- `pipeline.png`
- `resume_tailor.png`
- `market_insights.png`
- `settings.png`

### Two paths

**A. You take them locally.** 5 minutes with Win+Shift+S. Drop them in
`docs/screenshots/`, I commit them.

**B. I install Playwright + headless Chromium.** ~180 MB browser
download, scripts capture each tab via JS-driven navigation. Ends up as
`scripts/capture_screenshots.py` callable on demand.

**My rec: A.** The Playwright route is brittle (Streamlit's tab JS state
is hard to drive headlessly) and the dev-time cost-to-benefit isn't
there for a one-time README task. If you want screenshot capture to be
part of CI for future regressions, that's a Phase 5 concern.

### Commit shape

1. `docs: add dashboard screenshots`

---

## Total commit count

≈ 8 commits across Phase 4. I'd label the last one
`feat: phase 4 - cron + cloud deploy + screenshots` per the prior phases'
pattern.

## Open questions for you to call

1. DB-storage decision (A / B / C / D / E above). **Default: B.**
2. Public vs auth-gated demo. **Default: public.**
3. Deploy from `main` or `demo` branch. **Default: main.**
4. Hide Pipeline + Settings in public mode. **Default: yes.**
5. Demo profile content — do you want me to derive it from a public-
   friendly resume PDF you'll provide, or hand-curate the criteria?
   **Default: hand-curated set covering data analyst + adjacent entry-
   level roles, no resume needed.**
6. Screenshots: A (you take) or B (I install Playwright). **Default: A.**

If you reply "all defaults", I'll execute the plan as written. Otherwise
tell me which numbers to change and I'll re-spin the affected sections.
