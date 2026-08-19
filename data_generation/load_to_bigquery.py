#!/usr/bin/env python3
"""
Load the generated CSVs into BigQuery.

Uses batch load jobs (not streaming inserts) because BigQuery Sandbox does
not support streaming ingestion. WRITE_TRUNCATE makes the load idempotent:
re-running converges to the same state rather than appending duplicates.

Usage:
    python data_generation/load_to_bigquery.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()

PROJECT = os.getenv("GCP_PROJECT_ID")
DATASET = os.getenv("BQ_DATASET_RAW")
LOCATION = os.getenv("BQ_LOCATION", "US")
IN = Path(__file__).resolve().parent / "output"

BQ = bigquery.SchemaField
S = "STRING"; I = "INTEGER"; F = "FLOAT"; D = "DATE"; B = "BOOLEAN"

SCHEMAS: dict[str, list] = {
    "customers": [
        BQ("cust_id", S, "REQUIRED"), BQ("cust_name", S), BQ("region", S),
        BQ("segment", S), BQ("industry", S), BQ("customer_since", D),
        BQ("behaviour_cohort", S), BQ("account_owner", S), BQ("is_internal", B),
    ],
    "products": [
        BQ("product_id", S, "REQUIRED"), BQ("product_name", S),
        BQ("product_platform", S), BQ("sku_tier", S),
        BQ("consumption_model", S), BQ("list_price_per_unit", F),
    ],
    "features": [
        BQ("feature_id", S, "REQUIRED"), BQ("product_id", S, "REQUIRED"),
        BQ("feature_name", S), BQ("feature_description", S),
        BQ("feature_tier", S), BQ("feature_value_weight", I),
    ],
    "entitlements": [
        BQ("entitlement_id", S, "REQUIRED"), BQ("cust_id", S, "REQUIRED"),
        BQ("product_id", S, "REQUIRED"), BQ("units_purchased", I),
        BQ("licensed_amount", F), BQ("start_date", D), BQ("end_date", D),
        BQ("contract_type", S), BQ("currency", S), BQ("fx_rate_to_usd", F),
        BQ("is_unlimited", B),
    ],
    "consumption_monthly": [
        BQ("entitlement_id", S, "REQUIRED"), BQ("cust_id", S), BQ("product_id", S),
        BQ("month", D, "REQUIRED"), BQ("consumed_units", F),
        BQ("licensed_amount_month", F),
    ],
    "feature_adoption_monthly": [
        BQ("entitlement_id", S, "REQUIRED"), BQ("cust_id", S), BQ("product_id", S),
        BQ("feature_id", S, "REQUIRED"), BQ("month", D, "REQUIRED"),
        BQ("is_active", B), BQ("usage_events", I), BQ("active_users", I),
    ],
    "deployment_events": [
        BQ("entitlement_id", S, "REQUIRED"), BQ("cust_id", S), BQ("product_id", S),
        BQ("event_type", S), BQ("event_date", D),
    ],
}

# Clustering only — NO time partitioning. This is deliberate and the reason
# matters.
#
# The first version of this loader partitioned the monthly fact tables by
# `month`, because that is the correct production shape. In BigQuery Sandbox it
# silently destroyed the dataset: the sandbox expires partitions 60 days after
# the PARTITION's own date, so every partition older than ~2 months was dropped
# at load time. 5,061 consumption rows became 348. The load job reported success.
#
# Lesson kept in the code rather than only in the deck: a production best
# practice can be actively harmful in the target environment, and "the job
# succeeded" is not the same as "the data is correct". Row-count verification
# below is what turns that from a silent failure into a loud one.
#
# In a production project with billing enabled, partitioning by `month` with
# `require_partition_filter` is the right call at scale.
CLUSTERING = {
    "consumption_monthly": ["cust_id", "product_id"],
    "feature_adoption_monthly": ["cust_id", "product_id"],
}

DATE_COLS = {"customer_since", "start_date", "end_date", "month", "event_date"}


def main() -> int:
    if not (PROJECT and DATASET):
        sys.exit("ABORT: GCP_PROJECT_ID / BQ_DATASET_RAW missing from .env")
    if not IN.exists():
        sys.exit("ABORT: no output/ folder — run generate_dataset.py first")

    client = bigquery.Client(project=PROJECT)
    print("=" * 68)
    print(f"Loading into {PROJECT}.{DATASET}  ({LOCATION})")
    print("=" * 68)

    failures = 0
    for table, schema in SCHEMAS.items():
        path = IN / f"{table}.csv"
        if not path.exists():
            print(f"  SKIP  {table}  (missing {path.name})")
            failures += 1
            continue

        df = pd.read_csv(path)
        for col in df.columns:
            if col in DATE_COLS:
                df[col] = pd.to_datetime(df[col]).dt.date

        job_config = bigquery.LoadJobConfig(
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        if table in CLUSTERING:
            job_config.clustering_fields = CLUSTERING[table]

        ref = f"{PROJECT}.{DATASET}.{table}"
        expected = len(df)
        try:
            # Drop before load. WRITE_TRUNCATE replaces ROWS but keeps the
            # existing table CONFIGURATION — so a table created with different
            # partitioning or clustering rejects the load with
            # "Incompatible table partitioning specification".
            #
            # Dropping makes the loader truly idempotent: it produces the same
            # result whether the table is absent, correct, or left over from an
            # earlier schema. That property matters more than the two seconds it
            # costs, because a reviewer running this from a clean clone should
            # never have to reason about prior state.
            client.delete_table(ref, not_found_ok=True)

            client.load_table_from_dataframe(
                df, ref, job_config=job_config, location=LOCATION
            ).result()
            n = client.get_table(ref).num_rows

            # Verify, don't assume. A load job can report success and still
            # land the wrong number of rows (partition expiry, silent drops,
            # schema coercion). Row parity is the cheapest possible check and
            # it is the one that would have caught the partitioning bug.
            if n != expected:
                print(f"  FAIL  {table:<26} loaded {n:,} rows, expected {expected:,} "
                      f"— {expected - n:,} rows lost")
                failures += 1
            else:
                print(f"  OK    {table:<26} {n:>7,} rows  (matches source)")
        except Exception as e:
            # Print the useful part of the error, not the HTTP envelope. The
            # first line of a BigQuery exception is usually the request URL,
            # which tells you nothing about what actually went wrong.
            detail = getattr(e, "errors", None)
            msg = (detail[0].get("message") if detail else None) or str(e)
            print(f"  FAIL  {table:<26} {msg[:300]}")
            failures += 1

    print("-" * 68)
    if failures:
        print(f"{failures} table(s) failed to load.")
        return 1
    print("All tables loaded. Next: python pipeline_and_tests/run_pipeline.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
