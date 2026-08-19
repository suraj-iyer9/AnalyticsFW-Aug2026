-- B1 dedupe + zero-fill against the spine.
--
-- The zero-fill is LOAD-BEARING FOR CORRECTNESS, not just completeness.
-- VRR is a product of two factors, so a NULL input propagates to a NULL output
-- - and NULL in this system means "deploying, too early to judge". A shelfware
-- account with a missing row would therefore be reported as a new account to
-- leave alone: the exact opposite of the correct action.
CREATE OR REPLACE TABLE `{{DM}}.stg_consumption` AS
WITH dedup AS (
  SELECT * EXCEPT(rn) FROM (
    SELECT c.*, ROW_NUMBER() OVER (
             PARTITION BY c.entitlement_id, c.month
             ORDER BY c.consumed_units DESC
           ) AS rn
    FROM `{{DR}}.consumption_monthly` c
  ) WHERE rn = 1
)
SELECT
  s.entitlement_id, s.cust_id, s.product_id, s.month,
  s.licensed_amount_month,
  s.is_unlimited,
  s.price_per_unit_usd,
  s.contract_value_month,
  COALESCE(d.consumed_units, 0) AS consumed_units,
  d.entitlement_id IS NULL       AS was_zero_filled
FROM `{{DM}}.stg_entitlement_month` s
LEFT JOIN dedup d
  ON d.entitlement_id = s.entitlement_id AND d.month = s.month;
