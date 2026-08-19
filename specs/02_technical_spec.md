# Technical Spec — Data Model, Pipeline, and Tests

**Companion to** `01_product_spec.md`. That document defines *what* we measure and why. This one defines *how* it is computed.

> **v2.0 changes:** aligned to the two-factor VRR; `int_persistence` deleted; model names now match spec terminology exactly; Value at Risk added; edge cases expanded from 5 to 12 across two families; zero-fill promoted from convention to tested correctness invariant; spec-to-model traceability table added.

---

## 1. Environment and constraints

| Item | Value |
|---|---|
| Warehouse | Google BigQuery **Sandbox** (free tier) |
| Project | `analyticsfw-productadoption` |
| Raw dataset | `ProductAdoption_raw` (US multi-region) |
| Marts dataset | `ProductAdoption_marts` (US multi-region) |
| Transform layer | dbt-style SQL executed via the BigQuery Python client |
| Tests | `pytest`, asserting against BigQuery query results |
| Dashboard | Streamlit + Plotly, reading the mart tables |

### 1.1 Binding constraint: no DML

BigQuery Sandbox does **not** support `INSERT` / `UPDATE` / `DELETE` / `MERGE`, streaming ingestion, or the Data Transfer Service. Verified empirically by `scripts/smoke_test_bigquery.py`, check 7 — not assumed from documentation.

**Design response:** every model is a full-refresh `CREATE OR REPLACE TABLE … AS SELECT`. Not a workaround; at this volume it is the better choice regardless:

- **Idempotent** — re-running converges to the same state
- **No state drift** — eliminates the class of bugs where an incremental model and a full rebuild disagree
- **Trivially reproducible** by a reviewer from a clean clone

At production volume the fact tables would move to incremental with partition-based merge; aggregate marts would stay full-refresh. That boundary is a volume decision, not an architectural one.

### 1.2 Configuration

No identifier is hardcoded. All scripts read `.env`:

```
GCP_PROJECT_ID, BQ_DATASET_RAW, BQ_DATASET_MART, BQ_LOCATION,
GOOGLE_APPLICATION_CREDENTIALS, RANDOM_SEED, MONTHS_HISTORY,
REPORTING_LAG_DAYS
```

The pipeline runs against any BigQuery project by changing one file.

### 1.3 Grain

**Every metric is computed at `customer × SKU × month`.** Every input must be a monthly figure; annual contract values are divided by term length before entering any calculation.

Enforced by test: twelve monthly values must sum back to contract value. Mixing an annual denominator with monthly activity is the most common error in consumption analytics and it fails silently — the result looks plausible and is wrong by a factor of twelve.

---

## 2. Source data model (`ProductAdoption_raw`)

| Table | Grain | Rows | Purpose |
|---|---|---|---|
| `customers` | 1 per customer | ~100 | Segment / region dimensions |
| `products` | 1 per SKU | ~500 | SKU catalogue, platform, commercial model |
| `features` | 1 per feature | ~2,000 | Feature catalogue with value tier and weight |
| `entitlements` | 1 per contract line | ~500 | What was sold, for how much, over what dates |
| `consumption_monthly` | entitlement × month | ~5,000 | Consumed vs licensed |
| `feature_adoption_monthly` | entitlement × feature × month | ~20,000 | Feature-level activity over time |
| `deployment_events` | entitlement × event | ~2,000 | Deployment milestones for TTFV |

### 2.1 Schemas

**`customers`** — `cust_id` (PK), `cust_name`, `region`, `segment`, `industry`, `customer_since`, `behaviour_cohort`, `is_internal`, `account_owner`

> `account_owner` (~6 fictional CSM names) exists solely to make product spec §7 demonstrable. Without an owner dimension, Value at Risk Recovered cannot be computed per rep, and the incentive proposal stays theoretical. One column converts it into a working dashboard view.

**`products`** — `product_id` (PK), `product_name`, `product_platform`, `sku_tier`, `consumption_model`, `list_price_per_unit`

**`features`** — `feature_id` (PK), `product_id` (FK), `feature_name`, `feature_description`, `feature_tier`, `feature_value_weight`

**`entitlements`** — `entitlement_id` (PK), `cust_id` (FK), `product_id` (FK), `units_purchased`, `licensed_amount`, `start_date`, `end_date`, `contract_type`, `currency`, `fx_rate_to_usd`, `is_unlimited`

**`consumption_monthly`** — `entitlement_id` (FK), `cust_id`, `product_id`, `month`, `consumed_units`, `licensed_amount_month`

**`feature_adoption_monthly`** — `entitlement_id` (FK), `cust_id`, `product_id`, `feature_id` (FK), `month`, `is_active`, `usage_events`, `active_users`

**`deployment_events`** — `entitlement_id` (FK), `cust_id`, `product_id`, `event_type`, `event_date`

### 2.2 What `consumed_units` means — one column, two commercial models

The product spec (§2.2) establishes that SKUs sell under two models. A single adoption metric must work across both, so one column carries both meanings:

| `products.consumption_model` | `licensed_amount` is | `consumed_units` is |
|---|---|---|
| `credits` | Capacity pool purchased for the term | Capacity drawn down |
| `licensed_units` | Seats / devices / nodes purchased | Seats / devices actively deployed |

`ConsumptionRate = consumed / licensed` is meaningful under both readings. This is deliberate: a metric that only understands seats is useless on a credit SKU and vice versa.

**Consequence for the tests:** the consumption tests must pass for both models. A test that only exercises credit-based SKUs would miss half the portfolio.

### 2.3 Invariants declared at generation

- Every product has ≥1 Core feature — otherwise `FeatureCoverage` has no lower bound
- `is_active` is **not cumulative**. A feature used in month 2 and abandoned in month 5 is inactive from month 5. Cumulative "ever adopted" flags are how abandonment becomes invisible.
- `behaviour_cohort` is **ground truth for tests only.** No pipeline model reads it. Metrics must detect these patterns from behaviour alone.

---

## 3. Injected edge cases — twelve, in two families

The brief specifies four. Family A covers those plus new deployments. **Family B is added beyond the brief** and is documented as such in the product spec §6.6.

### 3.1 Family A — customer behaviour

*What customers do. Assigned as a cohort label per customer; `expansion` is an independent overlay.*

| # | Case | Share | Generated behaviour |
|---|---|---|---|
| A1 | `spike_drop` | ~5% | 90% of annual entitlement burned in months 1–3, then ~0 |
| A2 | `shelfware` | ~10% | Zero consumption and zero feature activity for the whole term |
| A3 | `overage` | ~15% | 120–160% of entitlement, sustained, on a deliberately narrow feature set |
| A4 | `expansion` *(overlay)* | ~12 accounts | Second, larger contract on the same SKU starting mid-term |
| A5 | `deploying` | derived | Any entitlement under 90 days old |

### 3.2 Family B — data integrity

*What breaks in the plumbing. Injected independently of behaviour cohort.*

| # | Case | Injection | Why it is usually missed |
|---|---|---|---|
| B1 | **Duplicate rows** | ~2% of `consumption_monthly` rows duplicated | Duplicates make numbers look *better*. Nobody investigates a metric that improved. |
| B2 | **Unlimited entitlement** | ~5 entitlements with `is_unlimited = TRUE`, `licensed_amount = NULL` | Divide-by-zero either crashes the row or silently drops it |
| B3 | **Unentitled feature usage** | ~2% of adoption rows reference a feature outside the SKU | Coverage exceeds 100% and nobody questions a number above target |
| B4 | **Renewal gap** | ~8 customers get a 30–60 day gap between contracts | Gap months look identical to shelfware |
| B5 | **Late-arriving data** | Final `REPORTING_LAG_DAYS` of usage withheld | Every current period looks like a decline |
| B6 | **Internal / test accounts** | ~3 customers flagged `is_internal` | Sit in production data indefinitely because nobody owns removing them |
| B7 | **Multi-currency** | ~20% of contracts in EUR / GBP with `fx_rate_to_usd` | Only surfaces once a metric is expressed in money |

### 3.3 The three that change the metric, not just the data

Most of Family B is hygiene. Three are genuine design decisions:

**B2 — unlimited entitlements have no denominator.** A consumption rate cannot exist. The metric does not fake one:

```
VRR = feature_coverage                      -- when is_unlimited
VRR = consumption_rate × feature_coverage   -- otherwise
```

`consumption_rate` is `NULL` for these rows and they are reported as a separate `Unlimited` cohort. The alternative — substituting 1.0 — would silently inflate their VRR and make unlimited contracts look like the healthiest in the portfolio.

**B4 — renewal gaps introduce a third state.** Most frameworks have two: good and bad. There is a third:

| State | Meaning | Scored? |
|---|---|---|
| Active contract, usage | Normal | Yes |
| Active contract, no usage | **Shelfware** | Yes — VRR = 0 |
| **No active contract** | Not applicable | **No row at all** |

Gap months produce no fact row, so no shelfware flag can fire in them. Conflating the second and third states dispatches a CSM to rescue an account that was only waiting on procurement.

**B5 — a number can be correct but not final.** Usage data lands with lag. Without a cutoff, the current period always looks like a cliff. An exec asks what happened, the answer is "the data isn't in yet," and after that happens twice they stop believing the dashboard.

```
is_provisional = (month >= DATE_SUB(CURRENT_DATE(), INTERVAL @REPORTING_LAG_DAYS DAY))
```

**This is surfaced in the UI, not hidden.** The most recent period renders greyed with the label *"provisional · data through <date>."* Hiding it works until someone notices the number keeps changing; making the lag visible costs one line of UI and protects the credibility of everything else on the screen.

---

## 4. Pipeline (`pipeline_and_tests/sql/`)

Three layers, executed in order by `run_pipeline.py`.

### 4.1 Staging — `stg_*`

| Model | Purpose |
|---|---|
| `stg_customers` | Excludes `is_internal` accounts (**B6**) |
| `stg_entitlements` | Normalizes money to USD via `fx_rate_to_usd` (**B7**); sets `is_unlimited` (**B2**) |
| `stg_entitlement_daily` | Explodes each entitlement to one row per active day — foundation of overlap-safe denominators (**A4**) and of gap detection (**B4**) |
| `stg_entitlement_month_spine` | Dense entitlement × month grid for every month with an active contract |
| `stg_consumption` | Deduplicated (**B1**), joined to the spine, **zero-filled** |
| `stg_feature_activity` | Inner-joined to entitled features (**B3**); joined to `feature_value_weight` |

**Deduplication (B1)** — before any aggregation:

```sql
SELECT * EXCEPT(rn) FROM (
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY entitlement_id, month ORDER BY consumed_units DESC
  ) AS rn
  FROM raw.consumption_monthly
) WHERE rn = 1
```

**Overlap-safe denominator (A4)** — point-in-time snapshot, not a sum over days:

```sql
SELECT cust_id, product_id, month,
       SUM(licensed_amount_month) AS licensed_amount_month
FROM (
  SELECT DISTINCT cust_id, product_id, month, entitlement_id, licensed_amount_month
  FROM stg_entitlement_daily
  WHERE day = LAST_DAY(month)
)
GROUP BY 1,2,3
```

Two overlapping contracts contribute their combined capacity once, not once per day of overlap.

**The spine is load-bearing for correctness, not just completeness.** Because VRR is a product of two factors, a `NULL` input propagates to a `NULL` output — and `NULL` in this system means *"deploying, too early to judge."* A shelfware account with a missing consumption row would therefore be reported as a new account to leave alone: the exact opposite of the correct action. Zero-filling is what prevents that, and it is tested as an invariant rather than trusted as a convention.

### 4.2 Intermediate — `int_*`

Names match product spec terminology exactly, so a reader can move between spec and code without translation.

| Model | Computes |
|---|---|
| `int_consumption_rate` | `MIN(consumed, licensed) / licensed`, capped at 1.0; `NULL` when unlimited; plus uncapped `overage_ratio` |
| `int_feature_coverage` | Value-weighted active ÷ entitled feature weight |
| `int_deployment` | TTFV in days, Core-feature completion %, `days_since_start` |
| `int_flags` | `flag_shelfware`, `flag_spike_drop`, `flag_chronic_overage`, `flag_deploying`, `flag_unlimited`, `is_provisional` |

> `int_persistence` **deleted.** There is no persistence term. Because VRR is computed monthly, an account that stops using the product falls toward zero across successive rows. The time series is the persistence measure — a chart, not a table.

### 4.3 Marts — `mart_*`

| Model | Grain | Consumer |
|---|---|---|
| `mart_customer_sku_month` | customer × SKU × month | Base fact — VRR, both factors, all value columns |
| `mart_customer_adoption` | customer × month | **Required deliverable** |
| `mart_product_adoption` | product × month | **Required deliverable** |
| `mart_feature_adoption` | product × feature × month | Feature-level insight within SKU |
| `mart_owner_recovery` | account_owner × quarter | **Value at Risk Recovered** — implements product spec §7 |
| `mart_exec_summary` | month | Portfolio VRR, cohort counts, annualized value at risk |

**VRR:**

```sql
CASE
  WHEN flag_deploying THEN NULL                          -- deliberately not scored
  WHEN flag_unlimited THEN feature_coverage              -- B2: no denominator exists
  ELSE COALESCE(consumption_rate, 0) * COALESCE(feature_coverage, 0)
END AS vrr
```

The explicit zero-guard from v1.0 is gone — multiplication already returns zero. The `COALESCE` calls exist for a different reason: they are the last line of defence ensuring a missing value can never be mistaken for a deliberate `NULL`.

**Value at Risk** — arithmetic on existing columns, so no separate model:

```sql
licensed_value_usd  =  licensed_amount_month * list_price_per_unit * fx_rate_to_usd
realized_value_usd  =  licensed_value_usd * vrr
value_at_risk_usd   =  licensed_value_usd * (1 - vrr)
```

Monthly figures are the stored source of truth. `mart_exec_summary` also exposes `annualized_value_at_risk_usd = monthly × 12`, labelled as a run rate in the UI.

> Adding an `int_value_at_risk` model was considered and rejected. A new model is justified when it changes grain or does real work; this is a multiplication.

### 4.4 `mart_owner_recovery` — Value at Risk Recovered

Implements product spec §7. Grain: `account_owner × quarter`.

```sql
WITH quarterly AS (
  SELECT
    c.account_owner,
    DATE_TRUNC(m.month, QUARTER)              AS quarter,
    SUM(m.value_at_risk_usd) * 12             AS annualized_var_usd,
    LOGICAL_AND(NOT m.is_provisional)         AS quarter_is_closed
  FROM mart_customer_sku_month m
  JOIN stg_customers c USING (cust_id)
  WHERE m.vrr IS NOT NULL                      -- exclude Deploying cohort
  GROUP BY 1, 2
)
SELECT
  account_owner,
  quarter,
  annualized_var_usd,
  LAG(annualized_var_usd) OVER (
    PARTITION BY account_owner ORDER BY quarter
  ) - annualized_var_usd                       AS value_at_risk_recovered_usd,
  LAG(annualized_var_usd) OVER (
    PARTITION BY account_owner ORDER BY quarter
  ) * 0.15                                     AS quota_usd,
  quarter_is_closed
FROM quarterly
WHERE quarter_is_closed                        -- see 4.5
```

`quota_usd` uses the placeholder 15% of opening at-risk book. Product spec §7.8 states plainly that this figure requires a year of history to calibrate.

### 4.5 Recovery is computed on closed periods only

Recovery compares a period's start to its end. The most recent period is marked `is_provisional` because usage data is still arriving (§3.2, B5). **A recovery figure ending on a provisional period would understate every rep's number and then silently correct upward later** — the worst possible property for anything attached to compensation.

**Rule:** `mart_owner_recovery` only emits rows for quarters where every constituent month is closed.

**Operational consequence, which Finance needs to know:** compensation figures lag by one reporting cycle. That is a real cost of the design and is stated rather than discovered.

---

## 5. Data quality tests (`pipeline_and_tests/tests/`)

`pytest`, run against live BigQuery. Split across two files so the distinction is visible in the folder structure, not buried in a comment:

- `test_synthetic_data.py` — validates the generator (Group B below). Would not exist in production.
- `test_data_quality.py` — validates the pipeline and the metric (Groups A, C, D).

### Group A — structural integrity
- Row counts within tolerance (~100 / ~500 / ~500 / ~2,000)
- No orphan foreign keys in any child table
- Every declared primary key is unique
- ≥12 months of history
- Every product has ≥1 Core feature

### Group B — anomaly injection *(tests the generator)*
- `spike_drop` share ∈ [3%, 7%]
- `shelfware` share ∈ [8%, 12%]
- `overage` share ∈ [13%, 17%]
- ≥1 customer with ≥2 temporally overlapping active entitlements
- Duplicate rows present before dedup; absent after
- ≥1 unlimited entitlement, ≥1 renewal gap, ≥1 internal account, ≥1 non-USD contract

### Group C — metric correctness against ground truth

*The group that matters. Groups A and D prove the pipeline ran; this proves it was right.*

| Test | Asserts |
|---|---|
| Shelfware scores zero | Every `shelfware` account: VRR = 0 and `flag_shelfware` |
| **Shelfware is 0, never NULL** | No shelfware account is misclassified as `Deploying` |
| Spike-and-drop decays | VRR high in months 1–3, near zero by month 6 — the curve shape, not a flag |
| Overage is capped | `consumption_rate ≤ 1.0` and `flag_chronic_overage` fired |
| Expansion doesn't break the denominator | Entitlement rises at expansion; no VRR collapse attributable to double-counting |
| Deploying is NULL | Under 90 days: VRR `NULL`, never `0` |
| Unlimited scores on coverage only | `consumption_rate IS NULL` and `vrr = feature_coverage` |
| Renewal gaps produce no rows | No fact row and no shelfware flag inside a gap |
| Internal accounts excluded | Zero rows in every mart |
| Both commercial models covered | Consumption assertions pass for `credits` and `licensed_units` SKUs alike |
| Recovery uses closed periods only | `mart_owner_recovery` contains no provisional quarter |
| Recovery reconciles | Recovered = prior-quarter at-risk − current-quarter at-risk, per owner, within 0.001 |
| Recovery can be negative | At least one owner-quarter has negative recovery — a declining book must reduce credit, not floor at zero |

### Group D — invariants

- Every active contract-month has **exactly one** row *(spine completeness; catches B1 and shelfware disappearance)*
- `consumption_rate` and `feature_coverage` are never `NULL` except where B2 requires it
- All rates ∈ [0, 1]; `feature_coverage` never exceeds 1.0 *(catches B3)*
- `vrr ∈ [0,1]` or `NULL`
- **Twelve monthly values sum to contract value** *(the grain trap)*
- Rollups reconcile to `mart_customer_sku_month` within 0.001
- All monetary columns are USD

**Provenance note worth stating aloud:** four of these tests exist because something went wrong during the build — the NULL propagation trap, the spine promotion, and the annual/monthly grain error. The suite is a record of mistakes made, not a checklist copied.

---

## 6. Dashboard (`dashboard/app.py`)

Streamlit, reading the mart tables.

| View | Contents |
|---|---|
| **Executive** | Portfolio VRR trend, annualized value at risk, cohort distribution, both factors side by side |
| **By Customer** | Sortable customer list with VRR, value at risk, flags; drill to SKU then feature |
| **By Product** | SKU league table; feature-level adoption heatmap within the selected SKU |
| **By Owner** | Value at Risk Recovered per rep per quarter, versus quota — makes product spec §7 demonstrable rather than theoretical |

**Design rules:**

- Every screen shows both factors alongside VRR — the apex is never displayed alone
- Every flagged account exposes the specific unadopted high-weight features, so the view ends in an action rather than a number
- **The provisional period is rendered greyed with an explicit label** — *"provisional · data through <date>"* — never hidden and never silently included

Streamlit is a deliberate speed trade-off. The deliverable is a decision, not a product.

---

## 7. Reproducibility

```bash
cp .env.example .env
python data_generation/generate_dataset.py
python data_generation/load_to_bigquery.py
python pipeline_and_tests/run_pipeline.py
pytest pipeline_and_tests/tests/ -v
streamlit run dashboard/app.py
```

`RANDOM_SEED=42` makes generation deterministic, so test assertions are stable.

**Sandbox note:** tables expire 60 days after creation. The sequence above rebuilds from scratch, so an expired environment is a re-run, not a rebuild.

---

## 8. Spec-to-model traceability

Every product spec section maps to an implementing model and an enforcing test.

| Product spec § | Concept | Model | Test |
|---|---|---|---|
| 4.2 | ConsumptionRate | `int_consumption_rate` | rates ∈ [0,1]; overage capped |
| 4.2 | FeatureCoverage | `int_feature_coverage` | coverage ≤ 1.0 |
| 4.2 | VRR | `mart_customer_sku_month` | VRR ∈ [0,1] or NULL |
| 4.3 | Monthly grain | all models | 12 months sum to contract value |
| 4.5 | Expected VRR distribution | *(documentation only)* | — |
| 4.7 | Persistence as time series | *(no model — by design)* | spike-drop curve shape |
| 4.8 | Rollups | `mart_customer_adoption`, `mart_product_adoption` | rollups reconcile |
| 5 | Value at Risk | columns on `mart_customer_sku_month` | monetary columns all USD |
| 6.1–6.5 | Family A edge cases | `int_flags` | Group C |
| 6.6 | Family B edge cases | `stg_*` | Groups B, C, D |
| 7.2–7.4 | Value at Risk Recovered, quota, attainment | `mart_owner_recovery` | recovery reconciles; negative recovery exists |
| 7.6 | 90-day sustain guardrail | `mart_owner_recovery` (provisional flag) | recovery uses closed periods only |
| 7.5 | Stage-gate component | `int_deployment` | deploying cohort is NULL |

---

## 9. AI-assisted development method

Spec-driven, in strict order:

1. **Spec first.** Both specs were written and committed before implementation code. Verifiable in `git log`.
2. **Specs as the generation contract.** Each script was generated from the relevant spec section, with the spec supplied as context.
3. **Tests derived from the spec, not the code.** Group C is generated from product spec §6, so tests assert *intended* behaviour rather than re-describing whatever the implementation happens to do.
4. **Regenerate, don't patch.** When the metric changed from a three-factor geometric mean to a two-factor product, the spec was amended and the affected models were regenerated from it — including deleting `int_persistence` outright rather than leaving it orphaned.

The specs are the source of truth. The code is an artifact of them.
