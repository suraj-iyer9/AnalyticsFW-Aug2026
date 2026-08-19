-- REQUIRED DELIVERABLE: adoption at the Product (SKU) level.
CREATE OR REPLACE TABLE `{{DM}}.mart_product_adoption` AS
SELECT
  product_id, product_name, product_platform, sku_tier, consumption_model, month,
  COUNT(DISTINCT cust_id)                                      AS customers,
  SUM(licensed_value_usd)                                      AS licensed_value_usd,
  SUM(realized_value_usd)                                      AS realized_value_usd,
  SUM(value_at_risk_usd)                                       AS value_at_risk_usd,
  SAFE_DIVIDE(SUM(vrr * licensed_value_usd),
              SUM(IF(vrr IS NULL, NULL, licensed_value_usd)))  AS vrr_value_weighted,
  AVG(vrr)                                                     AS vrr_unweighted,
  AVG(consumption_rate)                                        AS consumption_rate,
  AVG(feature_coverage)                                        AS feature_coverage,
  COUNTIF(flag_shelfware)                                      AS customers_shelfware,
  COUNTIF(flag_chronic_overage)                                AS customers_overage,
  LOGICAL_OR(is_incomplete)                                   AS is_incomplete
FROM `{{DM}}.mart_customer_sku_month`
GROUP BY product_id, product_name, product_platform, sku_tier,
         consumption_model, month;
