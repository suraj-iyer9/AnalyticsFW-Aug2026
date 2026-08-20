#!/usr/bin/env python3
"""
BigQuery smoke test — verifies credentials, roles, and dataset config
BEFORE we write a single line of pipeline code.

Empirical beats theoretical: rather than reasoning about which IAM role
grants which permission, this asks BigQuery directly.

Run:  python scripts/smoke_test_bigquery.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

PROJECT = os.getenv("GCP_PROJECT_ID")
DS_RAW = os.getenv("BQ_DATASET_RAW")
DS_MART = os.getenv("BQ_DATASET_MART")
LOCATION = os.getenv("BQ_LOCATION", "US")
KEY = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

CHECKS = []


def check(name, fn):
    """Run one check, record PASS/FAIL, never raise."""
    try:
        detail = fn()
        CHECKS.append((True, name, detail or ""))
        print(f"  PASS  {name}" + (f"  →  {detail}" if detail else ""))
        return True
    except Exception as e:
        msg = str(e).split("\n")[0][:200]
        CHECKS.append((False, name, msg))
        print(f"  FAIL  {name}\n        {msg}")
        return False


print("=" * 68)
print("BigQuery smoke test")
print("=" * 68)
print(f"  project   : {PROJECT}")
print(f"  raw ds    : {DS_RAW}")
print(f"  mart ds   : {DS_MART}")
print(f"  location  : {LOCATION}")
print(f"  key file  : {KEY}")
print("-" * 68)

# ---- 0. Config sanity -------------------------------------------------
if not all([PROJECT, DS_RAW, DS_MART, KEY]):
    sys.exit("ABORT: .env is missing one or more required values.")

if not os.path.exists(KEY):
    sys.exit(f"ABORT: service account key not found at {KEY}")

from google.cloud import bigquery  # noqa: E402

client = bigquery.Client(project=PROJECT)

# ---- 1. Authentication ------------------------------------------------
check(
    "1. Authenticate as service account",
    lambda: client._credentials.service_account_email,
)

# ---- 2. Can list datasets (read) --------------------------------------
def _list():
    names = [d.dataset_id for d in client.list_datasets(PROJECT)]
    return f"{len(names)} dataset(s): {names}"


check("2. List datasets in project", _list)

# ---- 3. Raw dataset exists, correct location --------------------------
def _raw():
    ds = client.get_dataset(f"{PROJECT}.{DS_RAW}")
    if ds.location.upper() != LOCATION.upper():
        raise RuntimeError(
            f"location is {ds.location}, expected {LOCATION}. "
            "Datasets cannot be moved — it must be recreated."
        )
    return f"exists, location={ds.location}"


check(f"3. Raw dataset '{DS_RAW}' exists in {LOCATION}", _raw)

# ---- 4. Can run a query job (bigquery.jobs.create) --------------------
# THIS is the check that tells us whether 'BigQuery Studio User'
# was sufficient, or whether 'BigQuery Job User' must be added.
def _query():
    rows = list(client.query("SELECT 1 AS ok", location=LOCATION).result())
    return f"query returned {rows[0].ok}"


jobs_ok = check("4. Run a query job  [needs bigquery.jobs.create]", _query)

# ---- 5. Can create a dataset (needed for the marts dataset) -----------
def _create_ds():
    ds = bigquery.Dataset(f"{PROJECT}.{DS_MART}")
    ds.location = LOCATION
    client.create_dataset(ds, exists_ok=True)
    return f"'{DS_MART}' ready"


check("5. Create/verify marts dataset  [needs datasets.create]", _create_ds)

# ---- 6. Can create and drop a table (Data Editor) ---------------------
def _table():
    tid = f"{PROJECT}.{DS_RAW}._smoke_test"
    client.query(
        f"CREATE OR REPLACE TABLE `{tid}` AS SELECT 1 AS x, 'hello' AS y",
        location=LOCATION,
    ).result()
    n = list(client.query(f"SELECT COUNT(*) AS c FROM `{tid}`", location=LOCATION).result())[0].c
    client.delete_table(tid, not_found_ok=True)
    return f"CTAS wrote {n} row, table dropped"


check("6. CREATE TABLE AS SELECT + drop  [needs Data Editor]", _table)

# ---- 7. Confirm sandbox DML restriction (informational) ---------------
def _dml():
    tid = f"{PROJECT}.{DS_RAW}._smoke_dml"
    client.query(
        f"CREATE OR REPLACE TABLE `{tid}` AS SELECT 1 AS x", location=LOCATION
    ).result()
    try:
        client.query(f"INSERT INTO `{tid}` (x) VALUES (2)", location=LOCATION).result()
        return "DML ALLOWED (not a sandbox, or sandbox rules changed)"
    except Exception:
        return "DML blocked — confirms sandbox; pipeline uses CTAS (as designed)"
    finally:
        client.delete_table(tid, not_found_ok=True)


check("7. DML behaviour (informational)", _dml)

# ---- Summary ----------------------------------------------------------
print("-" * 68)
failed = [c for c in CHECKS if not c[0]]
if not failed:
    print("ALL CHECKS PASSED — environment is ready. Run the pipeline next.")
    sys.exit(0)

print(f"{len(failed)} CHECK(S) FAILED:")
for _, name, msg in failed:
    print(f"   • {name}\n     {msg}")

if not jobs_ok:
    print(
        "\nMOST LIKELY FIX — check 4 failed, so the service account cannot run jobs:\n"
        "  Console → IAM & Admin → IAM → find your service account → pencil icon\n"
        "  → + ADD ANOTHER ROLE → 'BigQuery Job User' → Save\n"
        "  Wait ~60s for IAM to propagate, then re-run this script."
    )
print("\nSee docs/SETUP.md for the full walkthrough.")
sys.exit(1)
