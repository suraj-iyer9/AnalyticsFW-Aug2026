-- Feature-level insight WITHIN each SKU - the brief asks for this explicitly.
-- This is the table that turns a score into a CSM worklist: which high-weight
-- features are entitled but unused, and what that gap is worth.
CREATE OR REPLACE TABLE `{{DM}}.mart_feature_adoption` AS
SELECT
  a.product_id, a.feature_id, a.feature_name, a.feature_tier,
  a.feature_value_weight, a.month,
  COUNT(DISTINCT a.cust_id)                                 AS customers_entitled,
  COUNT(DISTINCT IF(a.is_active, a.cust_id, NULL))          AS customers_active,
  SAFE_DIVIDE(COUNT(DISTINCT IF(a.is_active, a.cust_id, NULL)),
              COUNT(DISTINCT a.cust_id))                    AS adoption_rate,
  SUM(a.usage_events)                                       AS usage_events
FROM `{{DM}}.stg_feature_activity` a
GROUP BY a.product_id, a.feature_id, a.feature_name, a.feature_tier,
         a.feature_value_weight, a.month;
