-- Implements product spec section 7: Value at Risk RECOVERED.
-- Grain: account_owner x quarter.
--
-- This is what makes the incentive design real rather than theoretical: the
-- scoreboard (VRR) and the paycheck (dollars recovered) are the SAME
-- measurement, expressed in the form each audience can act on.
--
-- Recovery is computed on CLOSED quarters only. A recovery figure ending on a
-- still-filling period would understate every rep's number and then silently
-- correct upward later - the worst possible property for anything attached to
-- pay. The cost: comp figures lag one reporting cycle. Finance is told that
-- up front rather than discovering it after a disputed payout.
CREATE OR REPLACE TABLE `{{DM}}.mart_owner_recovery` AS
WITH quarterly AS (
  SELECT
    account_owner,
    DATE_TRUNC(month, QUARTER)                 AS quarter,
    SUM(value_at_risk_usd) * 12                AS annualized_var_usd,
    SUM(licensed_value_usd) * 12               AS annualized_book_usd,
    COUNT(DISTINCT cust_id)                    AS accounts,
    LOGICAL_AND(NOT is_incomplete)            AS quarter_is_complete
  FROM `{{DM}}.mart_customer_sku_month`
  WHERE vrr IS NOT NULL                        -- Deploying cohort excluded
  GROUP BY account_owner, quarter
),
seq AS (
  SELECT *,
    LAG(annualized_var_usd) OVER (
      PARTITION BY account_owner ORDER BY quarter) AS prior_var_usd
  FROM quarterly
  WHERE quarter_is_complete
)
SELECT
  account_owner, quarter, accounts,
  annualized_book_usd,
  prior_var_usd                                       AS opening_var_usd,
  annualized_var_usd                                  AS closing_var_usd,
  -- Can be NEGATIVE, deliberately. A rep whose book declines must LOSE credit;
  -- if this floored at zero, declining accounts become invisible and the whole
  -- incentive inverts.
  prior_var_usd - annualized_var_usd                  AS value_recovered_usd,
  prior_var_usd * 0.15                                AS quota_usd,
  SAFE_DIVIDE(prior_var_usd - annualized_var_usd,
              prior_var_usd * 0.15)                   AS quota_attainment
FROM seq
WHERE prior_var_usd IS NOT NULL;
