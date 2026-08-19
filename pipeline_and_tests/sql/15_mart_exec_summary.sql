-- One row per month. Feeds the executive view and the trust strip.
CREATE OR REPLACE TABLE `{{DM}}.mart_exec_summary` AS
SELECT
  month,
  COUNT(DISTINCT cust_id)                                      AS customers,
  COUNT(DISTINCT product_id)                                   AS skus,
  SUM(licensed_value_usd)                                      AS licensed_value_usd,
  SUM(realized_value_usd)                                      AS realized_value_usd,
  SUM(value_at_risk_usd)                                       AS value_at_risk_usd,
  SUM(value_at_risk_usd) * 12                                  AS annualized_var_usd,
  SAFE_DIVIDE(SUM(vrr * licensed_value_usd),
              SUM(IF(vrr IS NULL, NULL, licensed_value_usd)))  AS vrr_value_weighted,
  AVG(vrr)                                                     AS vrr_unweighted,
  AVG(consumption_rate)                                        AS consumption_rate,
  AVG(feature_coverage)                                        AS feature_coverage,
  COUNTIF(flag_shelfware)                                      AS n_shelfware,
  COUNTIF(flag_spike_drop)                                     AS n_spike_drop,
  COUNTIF(flag_chronic_overage)                                AS n_overage,
  COUNTIF(flag_deploying)                                      AS n_deploying,
  COUNTIF(flag_unlimited)                                      AS n_unlimited,
  LOGICAL_OR(is_incomplete)                                   AS is_incomplete
FROM `{{DM}}.mart_customer_sku_month`
GROUP BY month;
