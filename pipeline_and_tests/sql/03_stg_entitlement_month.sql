-- Point-in-time snapshot: one row per entitlement per month it is ACTIVE.
--
-- This is the overlap-safe denominator (A4). Two overlapping contracts each
-- contribute one row per month, so SUM() gives combined capacity ONCE - not
-- once per day of overlap.
--
-- B4 falls out for free: a month with no active contract produces no row, so
-- renewal-gap months are never scored. "No active contract" and "active
-- contract, no usage" stay distinct states.
CREATE OR REPLACE TABLE `{{DM}}.stg_entitlement_month` AS
WITH date_window AS (
  SELECT MIN(month) AS lo, MAX(month) AS hi FROM `{{DR}}.consumption_monthly`
)
SELECT
  e.entitlement_id, e.cust_id, e.product_id, e.product_name, e.product_platform,
  e.sku_tier, e.consumption_model, e.contract_type, e.is_unlimited,
  e.price_per_unit_usd, e.units_purchased, e.start_date, e.end_date,
  m AS month,
  -- annual entitlement -> monthly. NULL for unlimited: no denominator exists.
  IF(e.is_unlimited, NULL, e.licensed_amount / 12.0) AS licensed_amount_month,
  -- MONEY, not capacity. licensed_amount is entitled CONSUMPTION (credits or
  -- units of capacity); units_purchased is the COMMERCIAL quantity that was
  -- actually priced. Multiplying capacity by unit price inflates contract value
  -- by the credit multiplier - up to 120x. Kept as a separate, explicitly named
  -- column so the two can never be confused again.
  e.units_purchased * e.price_per_unit_usd / 12.0 AS contract_value_month
FROM `{{DM}}.stg_entitlements` e
CROSS JOIN date_window w
CROSS JOIN UNNEST(GENERATE_DATE_ARRAY(w.lo, w.hi, INTERVAL 1 MONTH)) AS m
WHERE LAST_DAY(m) >= e.start_date
  AND m            <= e.end_date;
