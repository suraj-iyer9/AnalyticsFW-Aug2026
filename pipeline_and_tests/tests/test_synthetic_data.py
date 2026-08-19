"""
GROUP B — validates the GENERATOR, not the pipeline.

These tests exist because this dataset is synthetic. They confirm the anomalies
the brief asked for were actually injected, at the specified rates. In a
production deployment this file would not exist.

It is kept in a separate file, rather than marked with a comment, so the
distinction between scaffolding and product is visible in the folder listing.
"""

from __future__ import annotations


# ---------------------------------------------------------- Family A ------
def test_spike_drop_share_is_about_5_percent(one):
    share = one("""
        SELECT COUNTIF(behaviour_cohort = 'spike_drop') / COUNT(*)
        FROM `{RAW}.customers`
    """)
    assert 0.03 <= share <= 0.07, f"spike_drop share is {share:.1%}"


def test_shelfware_share_is_about_10_percent(one):
    share = one("""
        SELECT COUNTIF(behaviour_cohort = 'shelfware') / COUNT(*)
        FROM `{RAW}.customers`
    """)
    assert 0.08 <= share <= 0.12, f"shelfware share is {share:.1%}"


def test_overage_share_is_about_15_percent(one):
    share = one("""
        SELECT COUNTIF(behaviour_cohort = 'overage') / COUNT(*)
        FROM `{RAW}.customers`
    """)
    assert 0.13 <= share <= 0.17, f"overage share is {share:.1%}"


def test_overlapping_entitlements_exist(one):
    """Mid-year expansion: two active contracts on the same SKU at once."""
    n = one("""
        SELECT COUNT(*) FROM (
          SELECT a.entitlement_id
          FROM `{RAW}.entitlements` a
          JOIN `{RAW}.entitlements` b
            ON a.cust_id = b.cust_id AND a.product_id = b.product_id
           AND a.entitlement_id != b.entitlement_id
           AND a.start_date <= b.end_date AND b.start_date <= a.end_date
        )
    """)
    assert n >= 2, "no overlapping entitlements were generated"


# ---------------------------------------------------------- Family B ------
def test_duplicate_rows_present_in_raw(one):
    """B1 — duplicates must exist BEFORE the pipeline, or dedupe proves nothing."""
    dupes = one("""
        SELECT COUNT(*) - COUNT(DISTINCT FORMAT('%s|%t', entitlement_id, month))
        FROM `{RAW}.consumption_monthly`
    """)
    assert dupes > 0, "no duplicate contract-months were injected"


def test_unlimited_entitlements_exist(one):
    n = one("SELECT COUNTIF(is_unlimited) FROM `{RAW}.entitlements`")
    assert n >= 1, "no unlimited contracts were generated"


def test_unlimited_entitlements_have_no_licensed_amount(one):
    """The whole point of B2: there is genuinely no denominator."""
    bad = one("""
        SELECT COUNTIF(licensed_amount IS NOT NULL)
        FROM `{RAW}.entitlements` WHERE is_unlimited
    """)
    assert bad == 0, "unlimited contracts should have NULL licensed_amount"


def test_unentitled_feature_usage_exists(one):
    """B3 — usage recorded against features outside the SKU."""
    n = one("""
        SELECT COUNT(*) FROM `{RAW}.feature_adoption_monthly` a
        LEFT JOIN `{RAW}.features` f
          ON f.feature_id = a.feature_id AND f.product_id = a.product_id
        WHERE f.feature_id IS NULL
    """)
    assert n > 0, "no unentitled feature usage was injected"


def test_renewal_gaps_exist(one):
    """B4 — a real hole between two contracts for the same customer + SKU."""
    n = one("""
        SELECT COUNT(*) FROM (
          SELECT a.entitlement_id
          FROM `{RAW}.entitlements` a
          JOIN `{RAW}.entitlements` b
            ON a.cust_id = b.cust_id AND a.product_id = b.product_id
           AND b.start_date > DATE_ADD(a.end_date, INTERVAL 31 DAY)
        )
    """)
    assert n >= 1, "no renewal gaps were generated"


def test_internal_accounts_exist(one):
    n = one("SELECT COUNTIF(is_internal) FROM `{RAW}.customers`")
    assert n >= 1, "no internal/test tenants were generated"


def test_non_usd_contracts_exist(one):
    share = one("""
        SELECT COUNTIF(currency != 'USD') / COUNT(*) FROM `{RAW}.entitlements`
    """)
    assert share > 0.05, f"only {share:.1%} of contracts are non-USD"


def test_latest_month_is_partially_loaded(one):
    """B5 — the current period must look incomplete, or the flag is untestable."""
    ratio = one("""
        WITH m AS (
          SELECT month, SUM(consumed_units) AS c
          FROM `{RAW}.consumption_monthly` GROUP BY month
        ), r AS (
          SELECT c, LAG(c) OVER (ORDER BY month) AS prev FROM m ORDER BY month DESC LIMIT 1
        )
        SELECT SAFE_DIVIDE(c, prev) FROM r
    """)
    assert ratio < 0.7, f"latest month is {ratio:.0%} of prior — not visibly incomplete"


# ------------------------------------------------------- structural -------
def test_row_counts_match_the_brief(one):
    for table, lo, hi in [
        ("customers", 90, 110),
        ("products", 450, 550),
        ("entitlements", 450, 550),
        ("features", 1800, 2200),
    ]:
        n = one(f"SELECT COUNT(*) FROM `{{RAW}}.{table}`")
        assert lo <= n <= hi, f"{table} has {n} rows, expected ~{(lo + hi) // 2}"


def test_at_least_twelve_months_of_history(one):
    n = one("SELECT COUNT(DISTINCT month) FROM `{RAW}.consumption_monthly`")
    assert n >= 12, f"only {n} months of history"


def test_every_product_has_a_core_feature(one):
    """Without a Core feature the coverage denominator has no meaningful floor."""
    missing = one("""
        SELECT COUNT(*) FROM (
          SELECT p.product_id FROM `{RAW}.products` p
          LEFT JOIN `{RAW}.features` f
            ON f.product_id = p.product_id AND f.feature_tier = 'Core'
          GROUP BY p.product_id
          HAVING COUNTIF(f.feature_id IS NOT NULL) = 0
        )
    """)
    assert missing == 0, f"{missing} products have no Core feature"


def test_no_orphan_foreign_keys(one):
    for child, parent, key in [
        ("entitlements", "customers", "cust_id"),
        ("entitlements", "products", "product_id"),
        ("features", "products", "product_id"),
        ("consumption_monthly", "entitlements", "entitlement_id"),
    ]:
        n = one(f"""
            SELECT COUNT(*) FROM `{{RAW}}.{child}` c
            LEFT JOIN `{{RAW}}.{parent}` p USING ({key})
            WHERE p.{key} IS NULL
        """)
        assert n == 0, f"{n} orphan rows in {child}.{key}"
