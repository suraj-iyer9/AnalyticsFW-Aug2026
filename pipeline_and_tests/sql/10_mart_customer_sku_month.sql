-- BASE FACT. Everything downstream reads this and nothing reads raw again.
-- Grain: customer x SKU x month.
CREATE OR REPLACE TABLE `{{DM}}.mart_customer_sku_month` AS
SELECT
  cu.cust_id, cu.cust_name, cu.segment, cu.region, cu.industry,
  cu.account_owner, cu.behaviour_cohort,          -- ground truth: tests only
  e.product_id, e.product_name, e.product_platform, e.sku_tier,
  e.consumption_model,
  r.month,

  r.consumed_units, r.licensed_amount_month, r.consumption_rate, r.overage_ratio,
  fc.feature_coverage, fc.active_features, fc.entitled_features,
  fc.active_weight, fc.entitled_weight,
  d.ttfv_days, d.days_since_start,

  fl.flag_shelfware, fl.flag_spike_drop, fl.flag_chronic_overage,
  fl.flag_deploying, fl.flag_unlimited, fl.is_incomplete,

  -- ---------------- VRR ------------------------------------------------
  -- Two percentages multiplied. No cube root, no weights to defend.
  --
  -- NULL and 0 mean OPPOSITE things here and must never collapse into each
  -- other: NULL = "deliberately not scored", 0 = "scored, and it is zero".
  -- The COALESCE calls are the last line of defence ensuring a missing value
  -- can never be mistaken for a deliberate NULL.
  CASE
    WHEN fl.flag_deploying THEN NULL                       -- too early to judge
    WHEN fl.flag_unlimited THEN fc.feature_coverage        -- B2: no denominator
    ELSE COALESCE(r.consumption_rate, 0) * COALESCE(fc.feature_coverage, 0)
  END AS vrr,

  -- ---------------- Money ----------------------------------------------
  -- Monthly, so twelve months reconcile to contract value. Mixing an annual
  -- denominator with monthly activity is the classic error in consumption
  -- analytics: it fails silently and is wrong by a factor of twelve.
  r.contract_value_month AS licensed_value_usd,
  r.contract_value_month * COALESCE(
    CASE
      WHEN fl.flag_deploying THEN NULL
      WHEN fl.flag_unlimited THEN fc.feature_coverage
      ELSE COALESCE(r.consumption_rate, 0) * COALESCE(fc.feature_coverage, 0)
    END, 0)                                      AS realized_value_usd,
  r.contract_value_month * (1 - COALESCE(
    CASE
      WHEN fl.flag_deploying THEN NULL
      WHEN fl.flag_unlimited THEN fc.feature_coverage
      ELSE COALESCE(r.consumption_rate, 0) * COALESCE(fc.feature_coverage, 0)
    END, 0))                                     AS value_at_risk_usd
FROM `{{DM}}.int_consumption_rate` r
JOIN `{{DM}}.stg_customers` cu USING (cust_id)
LEFT JOIN `{{DM}}.int_feature_coverage` fc USING (cust_id, product_id, month)
LEFT JOIN `{{DM}}.int_deployment`       d  USING (cust_id, product_id, month)
LEFT JOIN `{{DM}}.int_flags`            fl USING (cust_id, product_id, month)
JOIN (SELECT DISTINCT product_id, product_name, product_platform, sku_tier,
                      consumption_model
      FROM `{{DM}}.stg_entitlements`) e USING (product_id);
