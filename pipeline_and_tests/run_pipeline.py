#!/usr/bin/env python3
"""
Runs the dbt-style SQL models in order and records what each cleaning step did.

Two jobs, and the second is the one people skip:

  1. Execute the models.
  2. Record, per run, exactly which rows were removed and why.

Tests tell you pass or fail. The audit tells you what actually HAPPENED.
Silent cleaning is how data teams lose trust: a number moves, nobody can
explain it, and after that every number is questioned.

Outputs:
  - 15 tables in the marts dataset
  - <marts>.pipeline_audit          (appended, so run history accumulates)
  - reports/last_run.md             (human-readable, gitignored)
  - the same audit table printed to the console

Usage:  python pipeline_and_tests/run_pipeline.py
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parents[1] / ".env")
load_dotenv()

PROJECT = os.getenv("GCP_PROJECT_ID")
DS_RAW = os.getenv("BQ_DATASET_RAW")
DS_MART = os.getenv("BQ_DATASET_MART")
LOCATION = os.getenv("BQ_LOCATION", "US")

if not all([PROJECT, DS_RAW, DS_MART]):
    sys.exit("ABORT: GCP_PROJECT_ID / BQ_DATASET_RAW / BQ_DATASET_MART missing from .env")

RAW = f"{PROJECT}.{DS_RAW}"
MART = f"{PROJECT}.{DS_MART}"

client = bigquery.Client(project=PROJECT)
RUN_TS = pd.Timestamp.now("UTC").floor("s")
RUN_ID = RUN_TS.strftime("%Y%m%d%H%M%S")

audit_rows: list[dict] = []


def q(sql: str) -> pd.DataFrame:
    return client.query(sql, location=LOCATION).result().to_dataframe()


def scalar(sql: str):
    return q(sql).iloc[0, 0]


def record(layer, model, action, rows_in=None, rows_out=None, removed=None, note=""):
    audit_rows.append(
        {
            "run_id": RUN_ID,
            "run_ts": RUN_TS,
            "layer": layer,
            "model": model,
            "action": action,
            "rows_in": None if rows_in is None else int(rows_in),
            "rows_out": None if rows_out is None else int(rows_out),
            "rows_removed": None if removed is None else int(removed),
            "note": note,
        }
    )


# --------------------------------------------------------------- execute ---
def run_models() -> None:
    files = sorted((ROOT / "sql").glob("*.sql"))
    if not files:
        sys.exit("ABORT: no SQL files found in pipeline_and_tests/sql/")

    print("=" * 78)
    print(f"Running {len(files)} models  →  {MART}")
    print("=" * 78)

    for f in files:
        sql = f.read_text().replace("{{DR}}", RAW).replace("{{DM}}", MART)
        name = re.sub(r"^\d+_", "", f.stem)
        t0 = time.time()
        try:
            client.query(sql, location=LOCATION).result()
        except Exception as e:
            detail = getattr(e, "errors", None)
            msg = (detail[0].get("message") if detail else None) or str(e)
            print(f"  FAIL  {name:<28} {msg[:220]}")
            sys.exit(1)
        n = client.get_table(f"{MART}.{name}").num_rows
        layer = name.split("_")[0]
        print(f"  OK    {name:<28} {n:>8,} rows   {time.time() - t0:5.1f}s")
        record(layer, name, "model built", rows_out=n, note=f"{time.time() - t0:.1f}s")


# ----------------------------------------------------------------- audit ---
def audit_cleaning() -> None:
    """Quantify every row this pipeline dropped, added, or flagged."""

    # B1 — duplicate contract-months removed
    raw_c = scalar(f"SELECT COUNT(*) FROM `{RAW}.consumption_monthly`")
    uniq_c = scalar(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT entitlement_id, month "
        f"FROM `{RAW}.consumption_monthly`)"
    )
    record("stg", "stg_consumption", "dedupe", raw_c, uniq_c, raw_c - uniq_c,
           "B1 duplicate contract-month rows removed")

    # B6 — internal/test tenants excluded
    raw_cust = scalar(f"SELECT COUNT(*) FROM `{RAW}.customers`")
    stg_cust = scalar(f"SELECT COUNT(*) FROM `{MART}.stg_customers`")
    record("stg", "stg_customers", "exclude internal", raw_cust, stg_cust,
           raw_cust - stg_cust, "B6 internal/test tenants dropped")

    # B7 — currency normalised
    fx = scalar(
        f"SELECT COUNT(*) FROM `{RAW}.entitlements` WHERE currency != 'USD'"
    )
    record("stg", "stg_entitlements", "convert currency", None, None, 0,
           f"B7 {fx} non-USD contracts converted to USD")

    # B2 — unlimited contracts: no denominator exists
    unl = scalar(f"SELECT COUNT(*) FROM `{RAW}.entitlements` WHERE is_unlimited")
    record("stg", "stg_entitlements", "flag unlimited", None, None, 0,
           f"B2 {unl} contracts have no licensed amount; scored on coverage only")

    # Zero-fill — the anti-shelfware invariant
    zf = scalar(
        f"SELECT COUNTIF(was_zero_filled) FROM `{MART}.stg_consumption`"
    )
    tot = scalar(f"SELECT COUNT(*) FROM `{MART}.stg_consumption`")
    record("stg", "stg_consumption", "zero-fill", None, tot, -zf,
           f"{zf} contract-months had no usage row and were filled with 0, not NULL")

    # B3 — usage on features outside the SKU
    raw_a = scalar(f"SELECT COUNT(*) FROM `{RAW}.feature_adoption_monthly`")
    kept = scalar(
        f"SELECT COUNT(*) FROM `{RAW}.feature_adoption_monthly` a "
        f"JOIN `{RAW}.features` f "
        f"ON f.feature_id = a.feature_id AND f.product_id = a.product_id"
    )
    record("stg", "stg_feature_activity", "drop unentitled", raw_a, kept,
           raw_a - kept, "B3 usage recorded against features outside the SKU")

    # B4 — renewal-gap months excluded from scoring
    gaps = scalar(f"""
        SELECT COALESCE(SUM(expected - actual), 0) FROM (
          SELECT s.cust_id, s.product_id,
                 DATE_DIFF(MAX(s.month), MIN(s.month), MONTH) + 1 AS expected,
                 COUNT(DISTINCT s.month)                          AS actual
          FROM `{MART}.stg_entitlement_month` s
          GROUP BY 1, 2)
    """)
    record("stg", "stg_entitlement_month", "exclude gap months", None, None, gaps,
           "B4 months with no active contract — not scored, not shelfware")

    # B5 — provisional period
    incomplete = scalar(f"SELECT COUNTIF(is_incomplete) FROM `{MART}.int_flags`")
    prov_month = scalar(
        f"SELECT MAX(month) FROM `{MART}.int_flags` WHERE is_incomplete"
    )
    record("int", "int_flags", "mark incomplete", None, None, incomplete,
           f"B5 {prov_month:%Y-%m} data still loading — shown greyed, excluded from comp")

    # Flags raised
    for flag, label in [
        ("flag_shelfware", "A2 shelfware"),
        ("flag_spike_drop", "A1 spike & drop"),
        ("flag_chronic_overage", "A3 chronic overage"),
        ("flag_deploying", "A5 deploying (<90 days, not scored)"),
    ]:
        n = scalar(f"SELECT COUNTIF({flag}) FROM `{MART}.int_flags`")
        record("int", "int_flags", "flag raised", None, None, n,
               f"{label} — {n} customer-SKU-months")


def publish_audit(df: pd.DataFrame) -> None:
    cfg = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=[
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("run_ts", "TIMESTAMP"),
            bigquery.SchemaField("layer", "STRING"),
            bigquery.SchemaField("model", "STRING"),
            bigquery.SchemaField("action", "STRING"),
            bigquery.SchemaField("rows_in", "INTEGER"),
            bigquery.SchemaField("rows_out", "INTEGER"),
            bigquery.SchemaField("rows_removed", "INTEGER"),
            bigquery.SchemaField("note", "STRING"),
        ],
    )
    client.load_table_from_dataframe(
        df, f"{MART}.pipeline_audit", job_config=cfg, location=LOCATION
    ).result()


def write_report(df: pd.DataFrame) -> Path:
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    path = out / "last_run.md"
    clean = df[df.action != "model built"]
    built = df[df.action == "model built"]
    with path.open("w") as fh:
        fh.write(f"# Pipeline run report\n\n**Run:** {RUN_ID} · "
                 f"**UTC:** {RUN_TS}\n\n")
        fh.write("## What was cleaned\n\nEvery row this pipeline dropped, added, "
                 "or flagged, with the reason.\n\n")
        fh.write(clean[["layer", "model", "action", "rows_in", "rows_out",
                        "rows_removed", "note"]].to_markdown(index=False))
        fh.write("\n\n## Models built\n\n")
        fh.write(built[["layer", "model", "rows_out", "note"]].to_markdown(index=False))
        fh.write("\n")
    return path


def main() -> int:
    run_models()
    audit_cleaning()

    df = pd.DataFrame(audit_rows)

    print("\n" + "=" * 78)
    print("DATA QUALITY AUDIT — what this run actually did to your data")
    print("=" * 78)
    clean = df[df.action != "model built"]
    print(clean[["model", "action", "rows_in", "rows_out", "rows_removed", "note"]]
          .to_string(index=False, na_rep="—"))

    publish_audit(df)
    path = write_report(df)

    print("\n" + "-" * 78)
    print(f"  audit table : {MART}.pipeline_audit   (appended, run_id={RUN_ID})")
    print(f"  run report  : {path}")
    print("  next        : pytest pipeline_and_tests/tests/ -v")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
