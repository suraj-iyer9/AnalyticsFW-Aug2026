-- Factor 1 of VRR: how much of what they bought are they using?
-- Grain: customer x SKU x month.
--
-- Capped at 1.0 (A3). Over-consumption is a real signal but an EXPANSION
-- signal, not a health signal - if it could exceed 1.0 it would inflate
-- rollups and mask dormancy on another SKU. Uncapped overage_ratio is kept
-- alongside so nothing is lost.
CREATE OR REPLACE TABLE `{{DM}}.int_consumption_rate` AS
SELECT
  cust_id, product_id, month,
  SUM(consumed_units)                              AS consumed_units,
  SUM(licensed_amount_month)                       AS licensed_amount_month,
  LOGICAL_OR(is_unlimited)                         AS is_unlimited,
  MAX(price_per_unit_usd)                          AS price_per_unit_usd,
  SUM(contract_value_month)                        AS contract_value_month,
  LOGICAL_AND(was_zero_filled)                     AS all_months_zero_filled,
  -- B2: unlimited contracts get NULL, never a fabricated 1.0. Substituting a
  -- full score would make unlimited deals look like the healthiest accounts
  -- in the portfolio.
  IF(LOGICAL_OR(is_unlimited), NULL,
     LEAST(SAFE_DIVIDE(SUM(consumed_units), SUM(licensed_amount_month)), 1.0)
  )                                                AS consumption_rate,
  IF(LOGICAL_OR(is_unlimited), NULL,
     SAFE_DIVIDE(SUM(consumed_units), SUM(licensed_amount_month))
  )                                                AS overage_ratio
FROM `{{DM}}.stg_consumption`
GROUP BY cust_id, product_id, month;
