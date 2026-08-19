-- Layer-3 diagnostics. Every flag is derived from BEHAVIOUR, never from the
-- ground-truth cohort label - that column exists only so the tests can check
-- whether these flags rediscovered what was planted.
CREATE OR REPLACE TABLE `{{DM}}.int_flags` AS
WITH latest AS (SELECT MAX(month) AS max_month FROM `{{DM}}.stg_consumption`),
hist AS (
  SELECT cust_id, product_id, month, consumed_units,
         SUM(consumed_units) OVER (PARTITION BY cust_id, product_id)      AS total_consumed,
         SUM(consumed_units) OVER (
           PARTITION BY cust_id, product_id ORDER BY month
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)              AS cum_consumed,
         ROW_NUMBER() OVER (PARTITION BY cust_id, product_id ORDER BY month) AS month_idx,
         COUNT(*) OVER (PARTITION BY cust_id, product_id)                 AS n_months
  FROM (SELECT cust_id, product_id, month, SUM(consumed_units) AS consumed_units
        FROM `{{DM}}.stg_consumption` GROUP BY 1,2,3)
)
SELECT
  r.cust_id, r.product_id, r.month,
  -- A2: zero usage, 90+ days past contract start
  (r.consumed_units = 0 AND COALESCE(d.days_since_start, 0) >= 90) AS flag_shelfware,
  -- A1: front-loaded burn, then dormant. Detected from the CURVE, not a label.
  (h.month_idx > 3 AND r.consumed_units = 0
   AND h.total_consumed > 0
   AND SAFE_DIVIDE(
         SUM(r.consumed_units) OVER (PARTITION BY r.cust_id, r.product_id
                                     ORDER BY r.month ROWS BETWEEN UNBOUNDED PRECEDING AND 2 PRECEDING),
         h.total_consumed) >= 0.7)                                AS flag_spike_drop,
  -- A3: sustained over-consumption = expansion opportunity AND sizing failure
  (COALESCE(c.overage_ratio, 0) >= 1.2)                           AS flag_chronic_overage,
  -- A5: too new to judge
  (COALESCE(d.days_since_start, 0) < 90)                          AS flag_deploying,
  -- B2
  c.is_unlimited                                                  AS flag_unlimited,
  -- B5: this month is still loading. The number is real but not final.
  (r.month >= l.max_month)                                        AS is_incomplete
FROM (SELECT cust_id, product_id, month, SUM(consumed_units) AS consumed_units
      FROM `{{DM}}.stg_consumption` GROUP BY 1,2,3) r
JOIN hist h USING (cust_id, product_id, month)
LEFT JOIN `{{DM}}.int_consumption_rate` c USING (cust_id, product_id, month)
LEFT JOIN `{{DM}}.int_deployment`       d USING (cust_id, product_id, month)
CROSS JOIN latest l;
