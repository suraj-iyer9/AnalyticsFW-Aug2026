# Setup — from nothing to a running dashboard

About 25 minutes, most of it waiting on Google. Everything here uses the **free** BigQuery Sandbox — no credit card, no billing account.

If you already have a GCP project with BigQuery enabled, skip to [Step 4](#4-python-environment).

---

## 1 · Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with any Google account.
2. Click the project dropdown in the top bar → **New Project**.
3. Name it anything (e.g. `adoption-framework`). Note the **Project ID** — it's usually the name plus a number, and it is *not* the display name. You'll need it in Step 5.
4. Open [BigQuery](https://console.cloud.google.com/bigquery). The first visit enables the API automatically.

You are now in the Sandbox: 10 GB of storage and 1 TB of queries per month, free. This project uses a fraction of that.

> **The one Sandbox rule that matters:** tables expire 60 days after creation, and `INSERT` / `UPDATE` / `DELETE` are blocked. The pipeline is built for both constraints — every model is a full-refresh `CREATE OR REPLACE TABLE`, so re-running it rebuilds everything from scratch.

## 2 · Create the two datasets

In the BigQuery console, click the **⋮** next to your project name → **Create dataset**. Do this twice:

| Dataset ID | Location |
|---|---|
| `ProductAdoption_raw` | `US` |
| `ProductAdoption_marts` | `US` |

**Location must match between the two, and must match `BQ_LOCATION` in your `.env`.** Datasets cannot be moved after creation — a mismatch means deleting and recreating.

## 3 · Create a service account and download its key

1. **IAM & Admin → Service Accounts → Create service account.** Name it anything.
2. Grant it **two** roles:
   - **BigQuery Data Editor** — create and drop tables
   - **BigQuery Job User** — run queries
3. Click the account → **Keys → Add key → Create new key → JSON**. The file downloads immediately.
4. **Move that file somewhere outside this repo.** The parent folder is a good default:

   ```bash
   mv ~/Downloads/your-project-abc123.json ../.gcp-key.json
   ```

> **Why outside the repo:** a service-account key is a live credential. `.gitignore` covers `.gcp-key.json` and `.env`, but the safest key is one that was never in the tree at all.

## 4 · Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Python **3.10 or newer**. Built and tested on 3.12.

## 5 · Point `.env` at your project

```bash
cp .env.example .env
```

Then open `.env` and set three values:

| Variable | What to put |
|---|---|
| `GCP_PROJECT_ID` | The **Project ID** from Step 1 — not the display name |
| `GOOGLE_APPLICATION_CREDENTIALS` | The **absolute** path to the key file from Step 3 |
| `BQ_LOCATION` | Must match the dataset location from Step 2 |

The rest (`RANDOM_SEED=42`, `MONTHS_HISTORY=15`) control the generated dataset. Leave them alone to reproduce the exact numbers in the deck.

`.env` is read from the repo root or from its parent, so either location works.

## 6 · Verify before you build

```bash
python scripts/smoke_test_bigquery.py
```

Seven checks, in the order they'd fail: authentication, dataset listing, dataset location, running a query job, creating a dataset, `CREATE TABLE AS SELECT` + drop, and DML behaviour. Expect:

```
ALL CHECKS PASSED — environment is ready. Run the pipeline next.
```

**Fix any failure here before continuing.** The most common one is check 4 — a service account with Data Editor but not Job User can create tables and cannot run queries. The script prints the fix. IAM changes take about 60 seconds to propagate.

## 7 · Run it

```bash
python data_generation/generate_dataset.py     # ~5s
python data_generation/load_to_bigquery.py     # ~30s
python pipeline_and_tests/run_pipeline.py      # ~60s
pytest pipeline_and_tests/tests/ -q            # ~40s
streamlit run dashboard/app.py
```

What each should print is in the README's [Run it](../README.md#run-it) table.

---

## When something breaks

| Symptom | Cause | Fix |
|---|---|---|
| `ABORT: .env is missing one or more required values` | `.env` not found or incomplete | Confirm it's in the repo root or its parent, and that all five keys have values |
| `403 ... bigquery.jobs.create denied` | Missing **BigQuery Job User** | Add the role, wait 60s, re-run the smoke test |
| `404 Not found: Dataset` | Typo, or dataset in a different region | Dataset IDs are case-sensitive; location must match `BQ_LOCATION` |
| `Table ... expired` after ~2 months | Sandbox 60-day expiry | Re-run steps 7.1–7.3; everything rebuilds deterministically |
| Dashboard is empty | Pipeline hasn't run, or ran against a different project | Check `run_pipeline.py` completed, and that `.env` points where you think |
| `ModuleNotFoundError` | Virtualenv not active | `source .venv/bin/activate` |

Everything is seeded from `RANDOM_SEED=42`, so a rebuild reproduces the same dataset and the same numbers every time.
