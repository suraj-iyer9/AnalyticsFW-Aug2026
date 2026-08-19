-- B7: all money normalised to USD here, once, so no downstream model has to
-- think about currency. B2: is_unlimited carried forward - those contracts have
-- no denominator and must not be given a fake one.
CREATE OR REPLACE TABLE `{{DM}}.stg_entitlements` AS
SELECT
  e.entitlement_id, e.cust_id, e.product_id,
  e.units_purchased, e.licensed_amount, e.start_date, e.end_date,
  e.contract_type, e.currency, e.is_unlimited,
  p.product_name, p.product_platform, p.sku_tier, p.consumption_model,
  p.list_price_per_unit * e.fx_rate_to_usd AS price_per_unit_usd
FROM `{{DR}}.entitlements` e
JOIN `{{DR}}.products`     p USING (product_id)
JOIN `{{DM}}.stg_customers` c USING (cust_id);   -- inner join drops internal accts
