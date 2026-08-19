"""Shared fixtures. Tests run against the live BigQuery marts."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from dotenv import load_dotenv
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT.parent / ".env")
load_dotenv()

PROJECT = os.getenv("GCP_PROJECT_ID")
RAW = f"{PROJECT}.{os.getenv('BQ_DATASET_RAW')}"
MART = f"{PROJECT}.{os.getenv('BQ_DATASET_MART')}"
LOCATION = os.getenv("BQ_LOCATION", "US")


@pytest.fixture(scope="session")
def bq():
    return bigquery.Client(project=PROJECT)


@pytest.fixture(scope="session")
def q(bq):
    """Run SQL, return a DataFrame. {RAW} and {MART} are substituted."""
    def _q(sql: str) -> pd.DataFrame:
        return bq.query(
            sql.format(RAW=RAW, MART=MART), location=LOCATION
        ).result().to_dataframe()
    return _q


@pytest.fixture(scope="session")
def one(q):
    """Run SQL, return a single scalar."""
    def _one(sql: str):
        return q(sql).iloc[0, 0]
    return _one


@pytest.fixture(scope="session")
def facts(q):
    """The base fact table, loaded once for the whole session."""
    return q("SELECT * FROM `{MART}.mart_customer_sku_month`")
