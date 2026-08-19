-- B6: internal/test tenants never reach any metric.
-- behaviour_cohort is carried through for the TEST SUITE ONLY. No downstream
-- model reads it; the metrics must rediscover those patterns from behaviour.
CREATE OR REPLACE TABLE `{{DM}}.stg_customers` AS
SELECT
  cust_id, cust_name, region, segment, industry, customer_since,
  account_owner, behaviour_cohort
FROM `{{DR}}.customers`
WHERE NOT is_internal;
