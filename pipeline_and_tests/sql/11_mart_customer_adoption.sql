-- REQUIRED DELIVERABLE: adoption at the Customer level.
-- Both weighted and unweighted VRR are exposed. The DIVERGENCE between them is
-- itself the finding: weighted >> unweighted means adoption succeeds in large
-- accounts and the mid-market motion is failing.
CREATE OR REPLACE TABLE `{{DM}}.mart_customer_adoption` AS
SELECT
  cust_id, cust_name, segment, region, industry, account_owner, month,
  COUNT(DISTINCT product_id)                                   AS skus_held,
  SUM(licensed_value_usd)                                      AS licensed_value_usd,
  SUM(realized_value_usd)                                      AS realized_value_usd,
  SUM(value_at_risk_usd)                                       AS value_at_risk_usd,
  SAFE_DIVIDE(SUM(vrr * licensed_value_usd),
              SUM(IF(vrr IS NULL, NULL, licensed_value_usd)))  AS vrr_value_weighted,
  AVG(vrr)                                                     AS vrr_unweighted,
  AVG(consumption_rate)                                        AS consumption_rate,
  AVG(feature_coverage)                                        AS feature_coverage,
  COUNTIF(flag_shelfware)                                      AS skus_shelfware,
  COUNTIF(flag_spike_drop)                                     AS skus_spike_drop,
  COUNTIF(flag_chronic_overage)                                AS skus_overage,
  COUNTIF(flag_deploying)                                      AS skus_deploying,
  LOGICAL_OR(is_incomplete)                                   AS is_incomplete
FROM `{{DM}}.mart_customer_sku_month`
GROUP BY cust_id, cust_name, segment, region, industry, account_owner, month;
