-- B3: INNER JOIN to the entitled feature set. Usage recorded against a feature
-- the customer never bought (trial access, mid-year repackaging) is discarded
-- here - otherwise feature coverage exceeds 100%, and a number above target is
-- rarely questioned.
-- Joining to the spine also restricts activity to months with an active contract.
CREATE OR REPLACE TABLE `{{DM}}.stg_feature_activity` AS
SELECT
  s.entitlement_id, s.cust_id, s.product_id, s.month,
  f.feature_id, f.feature_name, f.feature_tier, f.feature_value_weight,
  COALESCE(a.is_active, FALSE) AS is_active,
  COALESCE(a.usage_events, 0)  AS usage_events
FROM `{{DM}}.stg_entitlement_month` s
JOIN `{{DR}}.features` f
  ON f.product_id = s.product_id
LEFT JOIN `{{DR}}.feature_adoption_monthly` a
  ON  a.entitlement_id = s.entitlement_id
  AND a.month          = s.month
  AND a.feature_id     = f.feature_id;
