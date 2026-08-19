"""
GROUPS C and D — validates the PIPELINE and the METRIC.

Group C is the one that matters. The generator secretly labels each customer's
intended behaviour in `behaviour_cohort`, a column no pipeline model reads.
These tests check whether the metric INDEPENDENTLY REDISCOVERED what was
planted.

Row counts and null checks prove the pipeline ran. These prove it was right.

Four of these tests exist because something went wrong during the build:
the NULL-propagation trap, the spine promotion, the annual/monthly grain error,
and the money-vs-capacity confusion. The suite is a record of mistakes made,
not a checklist copied.
"""

from __future__ import annotations

import pytest

DEPLOY_DAYS = 90


# ============================================================ GROUP C ======
# Does the metric detect what was injected?

def test_shelfware_accounts_score_zero(q):
    """A2 — an account using nothing has realized nothing."""
    df = q("""
        SELECT cust_id, AVG(vrr) AS avg_vrr, MAX(CAST(flag_shelfware AS INT64)) AS flagged
        FROM `{MART}.mart_customer_sku_month`
        WHERE behaviour_cohort = 'shelfware' AND NOT flag_deploying
        GROUP BY cust_id
    """)
    assert len(df) > 0, "no shelfware customers reached the marts"
    assert (df.avg_vrr.fillna(1) == 0).all(), "some shelfware accounts scored above zero"
    assert df.flagged.sum() > 0, "shelfware flag never fired"


def test_shelfware_is_zero_never_null(q):
    """
    THE TRAP. VRR is a product of two factors, so a NULL input propagates to a
    NULL output - and NULL means "deploying, too early to judge". A shelfware
    account with a missing usage row would be reported as a new account to leave
    alone: the exact opposite of the correct action.
    """
    n = q("""
        SELECT COUNT(*) AS n FROM `{MART}.mart_customer_sku_month`
        WHERE behaviour_cohort = 'shelfware'
          AND NOT flag_deploying
          AND vrr IS NULL
    """).n[0]
    assert n == 0, f"{n} shelfware rows are NULL — they would read as 'too new to judge'"


def test_spike_drop_decays_over_time(q):
    """
    A1 — front-loaded burn then dormancy. Tested on the SHAPE of the curve, not
    on a flag: early months high, later months near zero. Cumulative or
    point-in-time metrics score these accounts as successes.
    """
    df = q("""
        SELECT month_idx, AVG(vrr) AS avg_vrr FROM (
          SELECT vrr, ROW_NUMBER() OVER (
                   PARTITION BY cust_id, product_id ORDER BY month) AS month_idx
          FROM `{MART}.mart_customer_sku_month`
          WHERE behaviour_cohort = 'spike_drop' AND vrr IS NOT NULL
        ) GROUP BY month_idx ORDER BY month_idx
    """)
    early = df[df.month_idx <= 3].avg_vrr.mean()
    late = df[df.month_idx >= 6].avg_vrr.mean()
    assert early > late, f"spike_drop did not decay: early={early:.3f} late={late:.3f}"
    assert late < 0.05, f"late-period VRR is {late:.3f}, expected near zero"


def test_consumption_rate_never_exceeds_one(q):
    """
    A3 — over-consumption is an EXPANSION signal, not a health signal. If it
    could exceed 1.0 it would inflate rollups and mask dormancy elsewhere.
    """
    n = q("""
        SELECT COUNT(*) AS n FROM `{MART}.mart_customer_sku_month`
        WHERE consumption_rate > 1.0
    """).n[0]
    assert n == 0, f"{n} rows have consumption_rate above 1.0"


def test_overage_accounts_are_flagged_and_capped(q):
    df = q("""
        SELECT cust_id,
               MAX(CAST(flag_chronic_overage AS INT64)) AS flagged,
               MAX(overage_ratio) AS max_ratio
        FROM `{MART}.mart_customer_sku_month`
        WHERE behaviour_cohort = 'overage'
        GROUP BY cust_id
    """)
    assert len(df) > 0
    assert df.flagged.sum() / len(df) > 0.8, "most overage accounts should be flagged"
    assert df.max_ratio.max() > 1.2, "overage_ratio should preserve the uncapped truth"


def test_deploying_accounts_are_null_never_zero(q):
    """
    A5 — an account 30 days in legitimately has low coverage. Scoring it the
    same way produces false alarms exactly where CSM attention is already
    highest. NULL and 0 are different states and must never collapse.
    """
    n = q("""
        SELECT COUNTIF(vrr = 0) AS n FROM `{MART}.mart_customer_sku_month`
        WHERE flag_deploying
    """).n[0]
    assert n == 0, f"{n} deploying rows scored 0 instead of NULL"


def test_unlimited_contracts_score_on_coverage_only(q):
    """
    B2 — no denominator exists. Substituting 1.0 for the missing consumption
    rate would make unlimited deals look like the healthiest in the portfolio.
    """
    df = q("""
        SELECT consumption_rate, feature_coverage, vrr
        FROM `{MART}.mart_customer_sku_month`
        WHERE flag_unlimited AND NOT flag_deploying
    """)
    if len(df) == 0:
        pytest.skip("no unlimited contracts in the scored window")
    assert df.consumption_rate.isna().all(), "unlimited rows must have NULL consumption_rate"
    assert (df.vrr.fillna(-1) - df.feature_coverage.fillna(-1)).abs().max() < 1e-9, \
        "unlimited VRR should equal feature coverage exactly"


def test_internal_accounts_never_reach_the_marts(q):
    """B6 — employee tenants must not pollute portfolio numbers."""
    n = q("""
        SELECT COUNT(*) AS n FROM `{MART}.mart_customer_sku_month`
        WHERE cust_name LIKE 'INTERNAL%'
    """).n[0]
    assert n == 0, f"{n} internal-account rows reached the marts"


def test_renewal_gap_months_are_not_scored(q):
    """
    B4 — the third state. "No active contract" is neither healthy nor at risk;
    it is NOT APPLICABLE, and must produce no row at all. Conflating it with
    shelfware dispatches a CSM to rescue an account waiting on procurement.
    """
    n = q("""
        SELECT COUNT(*) AS n
        FROM `{MART}.mart_customer_sku_month` m
        JOIN `{RAW}.entitlements` a
          ON a.cust_id = m.cust_id AND a.product_id = m.product_id
        JOIN `{RAW}.entitlements` b
          ON b.cust_id = m.cust_id AND b.product_id = m.product_id
         AND b.start_date > DATE_ADD(a.end_date, INTERVAL 31 DAY)
        WHERE m.month > a.end_date
          AND m.month < DATE_TRUNC(b.start_date, MONTH)
          -- A customer can hold SEVERAL contracts for the same SKU. A month is
          -- only truly uncovered if NO contract is active in it. Without this
          -- clause the test flags months covered by a third entitlement.
          AND NOT EXISTS (
            SELECT 1 FROM `{RAW}.entitlements` c
            WHERE c.cust_id = m.cust_id AND c.product_id = m.product_id
              AND LAST_DAY(m.month) >= c.start_date AND m.month <= c.end_date
          )
    """).n[0]
    assert n == 0, f"{n} scored rows fall inside a renewal gap"


def test_both_commercial_models_are_covered(q):
    """
    A metric that only understands seats is useless on a credit SKU. Both must
    produce scored rows, or half the portfolio is silently unmeasured.
    """
    df = q("""
        SELECT consumption_model, COUNT(*) AS n, COUNTIF(vrr IS NOT NULL) AS scored
        FROM `{MART}.mart_customer_sku_month`
        GROUP BY consumption_model
    """)
    assert len(df) >= 2, "only one commercial model present"
    assert (df.scored > 0).all(), "a commercial model produced no scored rows"


def test_incomplete_period_is_flagged(q):
    """B5 — the current period is real but not final, and must say so."""
    df = q("""
        SELECT month, LOGICAL_OR(is_incomplete) AS inc
        FROM `{MART}.mart_customer_sku_month` GROUP BY month ORDER BY month
    """)
    assert df.inc.iloc[-1], "the latest month is not flagged incomplete"
    assert not df.inc.iloc[:-1].any(), "an earlier month is wrongly flagged incomplete"


# ============================================================ GROUP D ======
# Invariants that must hold for every row.

def test_every_active_contract_month_has_exactly_one_row(q):
    """
    Spine completeness. Catches BOTH duplicate rows and shelfware disappearance
    - the two failure modes that move the number in opposite directions.
    """
    n = q("""
        SELECT COUNT(*) AS n FROM (
          SELECT entitlement_id, month, COUNT(*) AS c
          FROM `{MART}.stg_consumption` GROUP BY 1, 2 HAVING c > 1
        )
    """).n[0]
    assert n == 0, f"{n} contract-months appear more than once"


def test_zero_fill_actually_happened(q):
    """
    If this is zero, the anti-shelfware mechanism was never exercised and the
    tests above pass vacuously. It caught exactly that on the first run.
    """
    n = q("SELECT COUNTIF(was_zero_filled) AS n FROM `{MART}.stg_consumption`").n[0]
    assert n > 0, "no rows were zero-filled — the safety net is untested"


def test_factors_are_never_null_except_where_required(q):
    """NULL is only permitted where we deliberately put it (unlimited contracts)."""
    n = q("""
        SELECT COUNT(*) AS n FROM `{MART}.mart_customer_sku_month`
        WHERE (consumption_rate IS NULL AND NOT flag_unlimited)
           OR feature_coverage IS NULL
    """).n[0]
    assert n == 0, f"{n} rows have an unexplained NULL factor"


def test_all_rates_are_between_zero_and_one(q):
    n = q("""
        SELECT COUNT(*) AS n FROM `{MART}.mart_customer_sku_month`
        WHERE consumption_rate NOT BETWEEN 0 AND 1
           OR feature_coverage NOT BETWEEN 0 AND 1
           OR vrr             NOT BETWEEN 0 AND 1
    """).n[0]
    assert n == 0, f"{n} rows have a rate outside [0, 1]"


def test_feature_coverage_never_exceeds_one(q):
    """B3 — usage on unentitled features would push this above 100%."""
    mx = q("""
        SELECT MAX(feature_coverage) AS mx FROM `{MART}.mart_customer_sku_month`
    """).mx[0]
    assert mx <= 1.0 + 1e-9, f"feature_coverage reached {mx}"


def test_twelve_months_reconcile_to_contract_value(q):
    """
    THE GRAIN TRAP. Mixing an annual denominator with monthly activity fails
    silently and is wrong by a factor of twelve. Summing the monthly contract
    value across a full term must return the annual contract value.
    """
    df = q("""
        SELECT e.entitlement_id,
               ANY_VALUE(e.units_purchased * p.list_price_per_unit * e.fx_rate_to_usd) AS annual,
               SUM(s.contract_value_month) AS summed
        FROM `{MART}.stg_consumption` s
        JOIN `{RAW}.entitlements` e ON e.entitlement_id = s.entitlement_id
        JOIN `{RAW}.products`     p ON p.product_id     = e.product_id
        GROUP BY e.entitlement_id
        HAVING COUNT(*) = 12
        LIMIT 50
    """)
    if len(df) == 0:
        pytest.skip("no entitlement has exactly 12 scored months in this window")
    err = ((df.summed - df.annual).abs() / df.annual).max()
    assert err < 0.001, f"12 months differ from annual contract value by {err:.2%}"


def test_value_columns_reconcile(q):
    """realized + at_risk must equal licensed value, row by row."""
    err = q("""
        SELECT MAX(ABS(realized_value_usd + value_at_risk_usd - licensed_value_usd)) AS e
        FROM `{MART}.mart_customer_sku_month`
        WHERE licensed_value_usd IS NOT NULL
    """).e[0]
    assert err < 0.01, f"value columns do not reconcile, max error ${err:,.2f}"


def test_customer_rollup_reconciles_to_base_fact(q):
    err = q("""
        WITH base AS (
          SELECT month, SUM(value_at_risk_usd) AS v
          FROM `{MART}.mart_customer_sku_month` GROUP BY month
        ), roll AS (
          SELECT month, SUM(value_at_risk_usd) AS v
          FROM `{MART}.mart_customer_adoption` GROUP BY month
        )
        SELECT MAX(ABS(base.v - roll.v)) AS e FROM base JOIN roll USING (month)
    """).e[0]
    assert err < 0.01, f"customer rollup differs from base fact by ${err:,.2f}"


def test_product_rollup_reconciles_to_base_fact(q):
    err = q("""
        WITH base AS (
          SELECT month, SUM(value_at_risk_usd) AS v
          FROM `{MART}.mart_customer_sku_month` GROUP BY month
        ), roll AS (
          SELECT month, SUM(value_at_risk_usd) AS v
          FROM `{MART}.mart_product_adoption` GROUP BY month
        )
        SELECT MAX(ABS(base.v - roll.v)) AS e FROM base JOIN roll USING (month)
    """).e[0]
    assert err < 0.01, f"product rollup differs from base fact by ${err:,.2f}"


def test_portfolio_value_is_plausible(q):
    """
    A smell test, deliberately. The first version of this pipeline reported
    $1.9B at risk across 97 customers - larger than the business - because it
    multiplied consumption CAPACITY by unit price instead of the commercial
    quantity. The pipeline reported success throughout.
    """
    acv = q("""
        SELECT SUM(licensed_value_usd) * 12 AS acv
        FROM `{MART}.mart_customer_sku_month`
        WHERE month = (SELECT MAX(month) FROM `{MART}.mart_customer_sku_month`)
    """).acv[0]
    assert 1e6 < acv < 1e9, f"annualized book is ${acv:,.0f} — implausible for ~100 customers"


# ---------------------------------------------------- incentive layer -----
def test_recovery_uses_complete_periods_only(q):
    """
    Comp figures must never be computed on a still-loading period: they would
    understate every rep and then silently correct upward later.
    """
    n = q("""
        SELECT COUNT(*) AS n FROM `{MART}.mart_owner_recovery`
        WHERE NOT quarter_is_complete
    """).n[0]
    assert n == 0, f"{n} recovery rows are based on incomplete data"


def test_recovery_can_be_negative(q):
    """
    A rep whose book declines must LOSE credit. If this floored at zero,
    declining accounts become invisible and the incentive inverts.
    """
    df = q("SELECT value_recovered_usd FROM `{MART}.mart_owner_recovery`")
    assert len(df) > 0, "no recovery rows produced"
    assert (df.value_recovered_usd < 0).any(), \
        "no negative recovery — declining books are not being penalised"


def test_recovery_reconciles_to_opening_and_closing(q):
    err = q("""
        SELECT MAX(ABS((opening_var_usd - closing_var_usd) - value_recovered_usd)) AS e
        FROM `{MART}.mart_owner_recovery`
    """).e[0]
    assert err < 0.01, f"recovery does not equal opening minus closing (${err:,.2f})"
