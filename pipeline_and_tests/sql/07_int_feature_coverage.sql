-- Factor 2 of VRR: are they using the features that MATTER?
-- Value-weighted, not counted: Core=3, Differentiator=2, Adjacent=1.
--
-- A customer using 8 of 10 features but neither Core one is not at 80%.
-- is_active is deliberately NOT cumulative - a feature used in month 2 and
-- abandoned in month 5 stops counting in month 5. Cumulative "ever adopted"
-- flags are how abandonment becomes invisible.
CREATE OR REPLACE TABLE `{{DM}}.int_feature_coverage` AS
SELECT
  cust_id, product_id, month,
  SUM(IF(is_active, feature_value_weight, 0))      AS active_weight,
  SUM(feature_value_weight)                        AS entitled_weight,
  COUNTIF(is_active)                               AS active_features,
  COUNT(*)                                         AS entitled_features,
  SAFE_DIVIDE(SUM(IF(is_active, feature_value_weight, 0)),
              SUM(feature_value_weight))           AS feature_coverage
FROM `{{DM}}.stg_feature_activity`
GROUP BY cust_id, product_id, month;
