-- Journey-stage diagnostics: Time to First Value and days since contract start.
-- Feeds the Deploying stage gate (A5) and the incentive stage-gate component.
CREATE OR REPLACE TABLE `{{DM}}.int_deployment` AS
WITH ev AS (
  SELECT entitlement_id,
         MIN(IF(event_type = 'contract_start', event_date, NULL)) AS contract_start,
         MIN(IF(event_type = 'first_value',    event_date, NULL)) AS first_value,
         MIN(IF(event_type = 'core_complete',  event_date, NULL)) AS core_complete
  FROM `{{DR}}.deployment_events`
  GROUP BY entitlement_id
)
SELECT
  s.cust_id, s.product_id, s.month,
  MIN(DATE_DIFF(ev.first_value, ev.contract_start, DAY))     AS ttfv_days,
  MIN(DATE_DIFF(ev.core_complete, ev.contract_start, DAY))   AS core_complete_days,
  MAX(DATE_DIFF(LAST_DAY(s.month), s.start_date, DAY))       AS days_since_start
FROM `{{DM}}.stg_entitlement_month` s
LEFT JOIN ev USING (entitlement_id)
GROUP BY s.cust_id, s.product_id, s.month;
