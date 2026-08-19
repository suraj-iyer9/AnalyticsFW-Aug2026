# Product Spec — Product Adoption & Value Realization Framework

**Author:** Suraj · **Version:** 2.4 · **Status:** Proposal for Product LT review
**Audience:** Product leadership, GMs of Product, Customer Success leadership, Analytics leadership, Engineering

## Revision history

This spec was not written once. It was argued down through nine revisions, and the metric it started with is not the metric it ended with. The table below records what prompted each change, because the reasoning is more useful than the result.

| Ver | Prompted by | Change | Why it was better |
|---|---|---|---|
| 0.1 | Initial draft | Three-layer framework; VRR as a geometric mean of Utilization × Breadth × Persistence | Starting point |
| 1.0 | Design review | Value-weighted feature adoption (Core/Differentiator/Adjacent, 3/2/1) replaced naive feature counting | A customer using 8 of 10 features but neither Core one is not at 80% |
| 1.1 | Author review | Problem statement rebuilt around **four framing questions** — what we sell, how much, to whom, what they do with it | The original problem statement was a metric justification written backwards. Questions before formula. |
| 1.2 | Author review | Separated **facts from scores**: Q1–Q3 produce counts, only Q4 produces a metric | Attempting to force revenue and segment into the score was the wrong shape. Facts × score = money. |
| 1.3 | Author review | Added **Value at Risk** as the dollar expression of VRR | Ratios can't be summed across customers. Dollars can — which is what makes "who do we sell to" answerable at the executive level. |
| **2.0** | Panel-readiness review | **Replaced the geometric mean with two multiplied percentages.** Persistence deleted as a formula term. Added §2 "How this business works" before the metric. | A cube root of three factors is not explainable to a GM in a 15-minute slot. Explainability is a design requirement, not a polish step. Removing the third factor also revealed that persistence is a time series, not a term — simpler *and* more honest. |
| 2.1 | Consistency check | Fixed **grain**: all inputs monthly; worked example rebuilt; monthly stored, annualized presented | The example mixed an annual credit pool with a monthly dollar figure — the exact error the framework warns about, made in the framework's own worked example |
| 2.2 | Robustness review | Added **§6.6 — seven data-integrity edge cases** beyond the four in scope | The specified edge cases are all behavioural. Real data also breaks because the plumbing breaks, and that is where adoption metrics fail quietly. |
| 2.3 | Author challenge | **§7 rewritten around Value at Risk Recovered.** Compensation now derives directly from the metric rather than sitting beside it. | "Here is a metric, don't pay people on it" is not an answer to a question about incentives. The connection existed in Value at Risk the whole time. |
| **2.4** | Spec-to-spec verification | Added §4.5 expected VRR distribution; `account_owner` so §7 is implementable; recovery restricted to closed periods | A rep-level comp design with no rep in the data model is theory. The distribution table prevents a reader interpreting 0.30 as failure. |

**What changed most between 1.0 and 2.4:** the metric got *simpler* — three factors to two, a cube root to a multiplication — while the framework around it got substantially more complete. Five edge cases became twelve, and the incentive section went from a closing recommendation to a working comp mechanism with quota mechanics and named gaming failure modes.

---

## 1. Problem statement — the four framing questions

We sell a wide range of cybersecurity products, across many SKUs and many features, to many different kinds of customers. Two things follow from that, and we can't currently do either well:

- **Quantify what customers actually do with what we sold them** — who is using our products, and how.
- **Incentivize customer-facing teams** — sales, account executives, customer success — in a way that improves customer outcomes and our own.

Everything in this framework exists to answer four questions:

| # | Question | What it tells us |
|---|---|---|
| **Q1** | **What do we sell?** | The portfolio: platforms, SKUs, features |
| **Q2** | **How much do we sell?** | Quantity: units, capacity, dollars |
| **Q3** | **Who do we sell to?** | The customer: segment, region, firmographics |
| **Q4** | **What do customers do with what we sold them?** | Activity: which features get used, how much capacity gets consumed |

**Q1 through Q3 are facts.** They describe the book of business. Counts and dollars, no judgment attached.

**Q4 is the only question that measures performance** — and it is where growth actually comes from.

The value of the framework is in **connecting them**. Facts alone tell you what you sold. Activity alone tells you what people did. Multiply them and you get the thing leadership can act on: how much of what we sold is actually converting into value, and how many dollars are not.

### 1.1 What we can and cannot answer today

We can answer *"did they buy?"* and *"did they renew?"* We cannot answer the question in between:

> **Is this customer realizing the value they paid for — and if not, which feature of which SKU is the gap?**

Three consequences:

1. **We find churn risk at renewal**, when the fix costs a discount instead of a deployment engineer.
2. **Consumption gets mistaken for value.** An account burning its full credit pool on one feature while ignoring nine others reports as healthy.
3. **We can't direct Customer Success effort.** With no feature-level signal, attention goes to big accounts and loud ones rather than to fixable risk.

Leadership is simultaneously debating how to **incentivize customer-facing teams**. That raises the bar: a measurement framework that can't survive being turned into a comp plan isn't finished. §7 addresses it directly.

---

## 2. How this business works

The metric in §4 only makes sense once four things are on the table. This section is deliberately placed before the metric.

### 2.1 The hierarchy — customers don't buy features, they buy SKUs

```
Platform          →   SKU                    →   Features
Cortex                XSIAM Advanced             Threat Detection
                                                 Automated Triage
                                                 Extended Log Retention
                                                 Custom Playbooks
```

A customer purchases a **SKU**. The SKU contains **features**. They can use some, all, or none of them, and we bill them the same either way.

That gap between *what was bought* and *what is used* is the entire problem — and it's why the framework has to report at SKU level **and** at feature level within the SKU.

### 2.2 Two commercial models, one metric

SKUs are not all sold the same way:

| Model | What the customer buys | What "using it" means | Typical of |
|---|---|---|---|
| **Licensed units** | A fixed count of seats, devices, or nodes | How many are deployed and active | Network security appliances |
| **Credits / capacity** | A pool of consumption drawn down over the term | How much of the pool is consumed | SecOps and cloud platforms |

Any adoption metric has to work across both. This is a real design constraint, not a detail — a metric that only understands seats is useless on a credit-based SKU, and vice versa.

### 2.3 What a customer actually holds — entitlements

An **entitlement** is one contract line: a SKU, a quantity, a licensed amount, a start date, an end date.

A customer holds several at once. They renew. They expand mid-term, which creates **two overlapping active entitlements for the same SKU**. Any measurement that adds those two contracts together will double-count what the customer is entitled to and make a successful expansion look like a collapse in adoption. §6.4 handles this.

### 2.4 Why this forces the shape of the metric

Put the three together:

> A customer buys a **bundle of features** and consumes a **quantity of capacity**. So adoption cannot be one number. You have to know **how many of the features they use** and **how much of the capacity they use**.

That sentence is the metric. §4 is just arithmetic on it.

### 2.5 A single worked example, used throughout

**Acme Financial** · *Cortex XSIAM Advanced* · 10M credits · $100k / year · 4 features.

Every section below uses this same account, so the reader never has to re-orient.

---

## 3. The framework — three layers, three audiences

The four framing questions never change. **Only the altitude changes.** A CSM and the CPO ask the same four questions and need answers at different resolution.

| Framing question | **Layer 1 — Apex**<br>CPO · GM · Board | **Layer 2 — Dimensions**<br>GM · Product leadership | **Layer 3 — Diagnostics**<br>CSM · PM |
|---|---|---|---|
| **Q1 · What do we sell?** | Platforms, # SKUs | SKUs in my portfolio | Features on this contract |
| **Q2 · How much?** | Total units and dollars | Units and dollars per SKU | Units and dollars on this account |
| **Q3 · Who?** | # customers by segment and region | Which segments buy this SKU | This customer's profile |
| **Q4 · What do they do?** | Portfolio VRR; total Value at Risk | Which factor of VRR is failing, by SKU | Which features are unused; which flags fired |
| **Decision it drives** | Where to invest; how to package | Which SKU is failing, and how | Which account to call this week |

### 3.1 Design principles

Distinct from the four *framing questions* above. These are engineering constraints on the design.

| # | Principle | Consequence |
|---|---|---|
| 1 | **Explainability is a requirement, not a nice-to-have** | Two multiplied percentages. A GM can recompute any number by hand. |
| 2 | **Facts and scores stay separate** | Q1–Q3 produce counts. Only Q4 produces a score. Nobody argues about whether a customer count is "good." |
| 3 | **Consumption ≠ value** | Volume is only half the metric; breadth is the other half |
| 4 | **Not all features are equal** | Adoption is value-weighted, not counted |
| 5 | **Ratios diagnose, dollars prioritize** | VRR says what's wrong; Value at Risk says what it's worth fixing |
| 6 | **Zero is a measurement, not a missing row** | Shelfware is zero-filled, never dropped by a join |
| 7 | **Measurable ≠ comp-able** | The scoreboard metric and the incentive metric are deliberately different |
| 8 | **Time series over formula** | Where a trend can carry the meaning, don't build a term for it |

---

## 4. North Star metric — Value Realization Rate (VRR)

### 4.1 In one sentence

> **VRR is the share of what a customer paid for that they are actually using.**

Reported monthly, at the grain of `customer × SKU`.

### 4.2 The formula

```
VRR  =  FeatureCoverage  ×  ConsumptionRate
```

Two percentages, multiplied. Both between 0 and 1, so VRR is between 0 and 1.

**FeatureCoverage — how many of the features they bought are they using?**

```
                   Σ value_weight of features ACTIVE this month
FeatureCoverage = ──────────────────────────────────────────────
                   Σ value_weight of features ENTITLED in the SKU
```

A feature is **active** in a month if it had at least one usage event that month. Not "ever adopted" — a feature used in month 2 and abandoned in month 5 stops counting in month 5. Cumulative "ever adopted" flags are how abandonment becomes invisible.

**Feature value weights** — not all features are equal:

| Tier | Weight | Meaning |
|---|---|---|
| **Core** | 3 | The reason the SKU was bought. Non-adoption is a deployment failure. |
| **Differentiator** | 2 | Why us over a competitor. Drives renewal and expansion. |
| **Adjacent** | 1 | Drives stickiness, not the purchase decision. |

**ConsumptionRate — how much of the capacity they bought are they using?**

```
ConsumptionRate = MIN(consumed_units, licensed_amount) / licensed_amount
```

Capped at 1.0. Over-consumption does **not** raise the score — it is surfaced separately as an expansion signal (§6.3).

This is the term that makes the metric work across both commercial models: for credit SKUs it's capacity drawn down, for licensed SKUs it's units deployed.

### 4.3 Grain — everything is monthly

**VRR is computed at `customer × SKU × month`.** Every input must be a monthly figure. Annual contract values are divided by term length before they enter any calculation.

This is not a formality. Mixing an annual denominator with monthly activity is the most common error in consumption analytics, and it fails silently — the number looks plausible and is wrong by a factor of twelve. The pipeline enforces it with a test: **twelve monthly values must sum back to the contract total.**

### 4.4 Worked example — Acme Financial

Acme's contract: **$100k / year**, 10M credits / year, 4 features. Converted to monthly grain:

| | Per year | Per month |
|---|---|---|
| Contract value | $100k | $8.3k |
| Credit entitlement | 10M | 833k |

**Step 1 — split the monthly value across features by weight.**

| Feature | Tier | Weight | Share of $8.3k |
|---|---|---|---|
| Threat Detection | Core | 3 | $2.8k |
| Automated Triage | Core | 3 | $2.8k |
| Extended Log Retention | Differentiator | 2 | $1.8k |
| Custom Playbooks | Adjacent | 1 | $0.9k |
| **Total** | | **9** | **$8.3k** |

**Step 2 — count only the features active this month.** Acme used Threat Detection only.

```
FeatureCoverage = 3 / 9 = 33%
```

**Step 3 — apply this month's consumption rate.** Acme drew 667k of its 833k monthly credit entitlement.

```
ConsumptionRate = 667k / 833k = 80%
VRR             = 33% × 80%   = 26%
```

**Reading it:** Acme is consuming plenty of capacity, but funnelling all of it through one of four features. They bought a platform and deployed a point tool. That is a renewal risk neither consumption alone nor a feature checklist alone would have caught.

### 4.5 What a normal VRR looks like

A low VRR is not a failing grade. It is the finding. Expected shape of a real portfolio:

| VRR | Share of accounts | Reading |
|---|---|---|
| 0.00 | ~10% | Shelfware — nothing is happening |
| 0.10 – 0.40 | ~45% | Partially deployed — the largest opportunity |
| 0.40 – 0.70 | ~30% | Healthy |
| 0.70 + | ~15% | Fully deployed |

Most of the book sits between 0.2 and 0.5, because enterprise customers routinely deploy a fraction of what they buy. **Three very different accounts can share a score of 0.30:**

| Coverage | Consumption | VRR | Story |
|---|---|---|---|
| 33% | 90% | 0.30 | Uses one feature hard |
| 60% | 50% | 0.30 | Uses most features lightly |
| 44% | 68% | 0.30 | Middle of the road |

The apex says *how much*; the two factors say *what to do*. This is why VRR is never displayed alone.

> **There is no good absolute value for this metric in year one. It is a baseline.** What matters is the distribution and the direction. If every account scored 0.9, the metric would not be telling us anything.

### 4.6 Why multiply, and why only two factors

| Question | Answer |
|---|---|
| **Why multiply rather than average?** | Averaging lets a strong factor hide a weak one. A customer at 100% consumption and 10% coverage averages to 55% and looks mediocre; multiplied, they're at 10% and look like what they are. Imbalance *is* the risk. |
| **Why not three factors?** | An earlier version had a third term for persistence and combined all three with a geometric mean. It was more precise and much harder to explain. Persistence is now handled by measuring monthly (§4.5). Two factors, one multiplication — a GM follows it the first time. |
| **Why cap consumption at 1.0?** | Otherwise over-consumption on one SKU inflates a rollup and masks dormancy on another. Over-consumption is a real signal, but it's an expansion signal, not a health signal. |
| **What if a factor is zero?** | VRR is zero. Deliberate. A customer using no features has realized nothing regardless of capacity burned, and vice versa. |

### 4.7 Persistence is a chart, not a term

Because VRR is computed monthly, an account that stops using the product simply drops toward zero over successive months. **The time series is the persistence measure.** This replaces a trailing-window formula and is both simpler and more honest — the reader sees the decline rather than a number asserting it.

### 4.8 Rollups

VRR is a ratio, and ratios don't sum. Rolling up to customer, product, platform, or segment is **entitlement-value weighted**:

```
VRR(rollup) = Σ( VRR × licensed_value ) / Σ licensed_value
```

The unweighted mean is also computed and exposed. The **divergence between them is itself a finding**: if value-weighted VRR is materially higher than unweighted, adoption success is concentrated in large accounts and the mid-market motion is failing.

---

## 5. Value at Risk — the same truth in dollars

VRR diagnoses. It doesn't prioritize, because percentages can't be added across customers.

Computed at the same monthly grain as VRR:

```
LicensedValue(month)  =  licensed_amount(month) × price_per_unit
RealizedValue(month)  =  LicensedValue × VRR
ValueAtRisk(month)    =  LicensedValue × (1 − VRR)
```

**Acme, this month:** $8.3k × 26% = **$2.2k realized**, **$6.1k at risk**.

### 5.1 Monthly is the source of truth; annualized is the headline

| View | Statement | Nature |
|---|---|---|
| **Monthly** | "$1.2M of entitlement value did not convert this month" | A rate. Reconciles to contract value; what the tests assert. |
| **Annualized** | "$14M of contract value is at risk this year" | A total. Lands harder in a GM conversation. |

**Both are computed; monthly is stored.** The executive view multiplies by twelve and labels the result explicitly as **"annualized run-rate at risk."**

Two reasons for that label. It keeps the stored data auditable and reconcilable, and it answers the question a GM will ask — *"over what period?"* — before it's asked. The annualized figure assumes current adoption persists for twelve months. That assumption is stated on the slide rather than left implicit.

**Why this exists:**

- **Dollars add up.** Value at Risk sums cleanly to any cut — segment, region, platform, a GM's book. VRR cannot.
- **It makes Q3 answerable at the top.** "Who do we sell to" becomes decision-grade at the apex only when you can total risk by segment.
- **It gives leadership one sentence.** *"$14M of entitlement value isn't converting, and 60% of it sits in Mid-Market Cortex."* That is a resourcing decision. "Portfolio VRR is 0.62" is not.

**The pairing, stated for the deck:** VRR is the behavioural truth. Value at Risk is the same truth in the currency a GM allocates in. **One diagnoses, one funds.**

---

## 6. Edge-case handling

Four anomalies are present in the dataset by design. Each has an explicit mechanism and an automated test.

### 6.1 Spike & drop — ~5% of accounts
*Burn most of the entitlement in months 1–3, then stop.*

- **A naive metric calls this a success.** Cumulative consumption shows 90% used.
- **Mechanism:** monthly measurement. By month 4 both features and consumption go quiet, so **VRR → 0** on its own. No special formula.
- **Also flagged** as `flag_spike_drop` for CSM action.

### 6.2 Shelfware — ~10% of accounts
*No usage at all.*

- **The failure isn't the score, it's disappearance.** Accounts with no consumption rows vanish from an inner join and stop appearing in reporting entirely.
- **Mechanism:** the pipeline builds a dense **entitlement × month spine** and LEFT JOINs usage, zero-filling. Every active entitlement produces a row every month whether or not usage exists.
- **VRR = 0**, `flag_shelfware` fires at ≥90 days past start.

### 6.3 Chronic overage — ~15% of accounts
*Consume 120%+ of entitlement, persistently.*

- **A naive metric ranks these as the best accounts.**
- **Mechanism:** `MIN(consumed, licensed)` caps ConsumptionRate at 1.0. Overage isn't discarded — it surfaces as `overage_ratio` and `flag_chronic_overage` (≥120% for 3+ consecutive months).
- **Product reading:** chronic overage is simultaneously an expansion opportunity and a contract-sizing failure. It belongs in the pipeline review and the pricing review, not in the health score.

### 6.4 Mid-year expansion / overlapping entitlements
*A second, larger contract signed mid-term.*

- **A naive denominator double-counts**, and VRR appears to collapse in the exact month the customer expanded — the worst possible false signal, since expansion is a success event.
- **Mechanism:** `licensed_amount` comes from a **daily effective-dated entitlement snapshot**, taking the union of contracts active on the measurement date rather than the sum of contract rows.

### 6.5 New deployments — added beyond the brief
- A customer 30 days in legitimately has low coverage. Scoring them the same way produces false alarms exactly where CSM attention is already highest.
- **Mechanism:** entitlements under 90 days old are **excluded from the apex** (`NULL`, never `0`) and reported as a `Deploying` cohort measured on Time to First Value and Core-feature activation.

### 6.6 Edge cases beyond the brief — data integrity

The five cases above are all **behavioural**: things customers do. Real enterprise data is also messy for a different reason — **the plumbing breaks**. These seven were not specified in the brief. They are included deliberately, because in practice they are where adoption metrics fail quietly.

| # | Case | What happens | Why it is usually missed |
|---|---|---|---|
| B1 | **Duplicate rows** | A pipeline re-run emits the same contract-month twice; consumption doubles | Duplicates make numbers look *better*. Nobody investigates a metric that improved. |
| B2 | **Unlimited entitlement** | Contract sold as "unlimited" — there is no denominator | The row either crashes on divide-by-zero or is silently dropped from reporting |
| B3 | **Usage on unentitled features** | Trial access or a packaging change produces usage outside the SKU | Coverage exceeds 100%, and a number above target is rarely questioned |
| B4 | **Renewal gap** | Contract lapses 45 days during procurement, then renews | Gap months are indistinguishable from shelfware |
| B5 | **Late-arriving data** | Usage lands days after the period closes | Every current period looks like a decline |
| B6 | **Internal / test accounts** | Employee tenants sit in production data | Nobody owns removing them |
| B7 | **Multi-currency contracts** | EUR and GBP contracts summed with USD | Only surfaces once the metric is expressed in money |

**Three of these change the framework, not just the data quality rules:**

**B2 — some contracts have no denominator.** For unlimited entitlements, `VRR = FeatureCoverage` alone, and they are reported as a separate cohort. The alternative — substituting 100% for the missing consumption rate — would make unlimited contracts appear to be the healthiest accounts in the portfolio.

**B4 — there is a third state.** Not "healthy" and not "at risk," but **"not applicable."** A month with no active contract produces no score at all. Most adoption frameworks have only two states, which is why they dispatch CSMs to rescue accounts that were merely waiting on paperwork.

**B5 — a number can be correct but not final.** The most recent period is marked **provisional** and shown greyed in the dashboard with the date the data runs through. Hiding the lag works until an executive notices the current month keeps changing — after which they stop trusting every number on the page. Making it visible costs one line of UI and protects the credibility of everything else.

---

## 7. Incentive design

A co-equal objective, not an appendix. Leadership is actively debating exactly this.

**The recommendation in one line:** don't compensate on the VRR *score*. Compensate on the *dollars it moves*.

### 7.1 Why not compensate on the VRR score itself

| Problem | Why it breaks |
|---|---|
| **Reps inherit their book** | A rep handed a healthy book wins by doing nothing. A rep handed a broken one loses while doing everything right. You'd be paying for account assignment, not performance. |
| **Ratios don't add up** | VRR is a percentage. It can't be summed across a book, compared fairly between a rep with three small accounts and a rep with one large one, or aggregated into a quarterly number. |
| **The coverage term is gameable** | Compensate on feature coverage and you get activation theatre: enablement scripts run, checkboxes tick, customer behaviour doesn't change. |

### 7.2 The metric that does work — Value at Risk Recovered

```
Recovered  =  ValueAtRisk(period start)  −  ValueAtRisk(period end)
```

summed across the accounts in that rep's book, using annualized Value at Risk.

This is **derived directly from VRR**. The scoreboard and the paycheck are the same underlying measurement, expressed in the form each audience can act on.

### 7.3 Worked example — one CSM, one quarter

| Account | Contract | VRR start | At risk start | VRR end | At risk end | **Recovered** |
|---|---|---|---|---|---|---|
| A | $500k | 0.30 | $350k | 0.55 | $225k | **+$125k** |
| B | $200k | 0.00 | $200k | 0.40 | $120k | **+$80k** |
| C | $1,000k | 0.85 | $150k | 0.88 | $120k | **+$30k** |
| D | $300k | 0.60 | $120k | 0.50 | $150k | **−$30k** |
| E | $150k | 0.70 | $45k | 0.70 | $45k | **$0** |
| **Book** | | | **$865k** | | **$660k** | **+$205k** |

Reading the rows:

- **B** was total shelfware. Biggest win, because it started at zero.
- **C** was already healthy. Small credit — there was little left to recover.
- **D went backwards.** Credit is **negative**. Without negatives, a rep can ignore a declining account and still get paid for an improving one.
- **E** didn't move. No credit, no penalty.

### 7.4 Turning dollars into a paycheck — quota and attainment

A raw dollar figure means nothing on its own: $10k recovered is heroic on a $50k book and irrelevant on a $10M one. So it is comped exactly like a sales quota, **scaled to the book**:

```
Opening at-risk book                =  $865k
Quota (15% of opening at-risk)      =  $130k
Recovered                           =  $205k
Attainment                          =  158%
```

The recovery component of comp pays at 158% of target.

**This plugs into machinery that already exists.** Sales organizations already run quota, attainment, accelerators, and clawbacks. This adds a quota line to a working system rather than requiring a new one — which matters enormously, because a comp plan that needs new infrastructure doesn't get implemented.

### 7.5 Proposed comp structure

| Weight | Component | Rationale |
|---|---|---|
| 50% | New business and expansion bookings | Unchanged. They still have to sell. |
| 30% | **Value at Risk recovered**, 90-day sustained | The new component, derived from VRR |
| 20% | Stage-gate progression — accounts moved `Deploying → Adopting` within 90 days | Rewards fast, clean deployments |

### 7.6 Why this is hard to game

Ask what gaming this metric would actually require. To move dollars from at-risk to realized, a customer must genuinely use more features, more consistently, for longer. That can't be faked with a webinar.

> **The design goal is a metric where the laziest way to win is the behaviour you wanted.**

**One guardrail is still required.** A rep could engineer a one-month usage spike and bank the recovery. So **recovered value is provisional until it holds for 90 days** — the same principle as a sales clawback on a cancelled deal.

**A second, operational rule follows from it.** Usage data arrives with lag, so the most recent period is always incomplete. Recovery is therefore computed **only on closed periods**. Calculating it on a still-filling period would understate every rep's number and then silently correct upward — the worst possible property for anything attached to pay.

**The cost, stated plainly:** compensation figures lag by one reporting cycle. Finance needs to know that before the plan ships, not after the first disputed payout.

**Published alongside, but not compensated on:**

- Share of accounts improving **from a low base** — catches cherry-picking the easy wins
- VRR spread within a rep's book — catches concentration on a few accounts
- Feature activations still active 90 days later — catches activation theatre

### 7.7 The second-order effect worth naming

Today nobody wants the shelfware account. Under this design, Account B — starting at zero — is the **most valuable opportunity** in the book.

**The metric inverts which accounts reps want to work.** That inversion, not the arithmetic, is the actual proposal.

### 7.8 Honest limitation — calibration

The quota percentage (15% above) is a judgment call, and it is the number Finance will argue about. It should be calibrated from a year of history: how much at-risk value does a good rep typically recover? Until that history exists, year one runs a deliberately soft target and is recalibrated afterwards.

**The mechanism is sound; the calibration needs data. Year one should be soft.**

### 7.9 The full chain

```
Feature usage  →  VRR  →  Value at Risk ($)  →  Recovered ($)  →  Quota attainment  →  Comp
   Q4 data        score      business lens        rep's delta       fair comparison     paycheck
```

Every step derives from the one before it. There is no separate incentive metric to maintain, reconcile, or argue about — the scoreboard and the paycheck are the same measurement.

---

## 8. Known limitations

Stated deliberately rather than discovered in review.

1. **Feature value weights are asserted, not derived.** 3/2/1 by tier is a product judgment. Deriving them from renewal correlation on *synthetic* data would mean fitting weights to patterns we injected ourselves — circular. §9 sets out the production path.
2. **Synthetic data validates mechanics, not predictive power.** The tests prove the logic handles the four anomalies. They cannot prove VRR predicts renewal. That needs a backtest against real churn history.
3. **Narrow-but-deep users score low.** A customer who deliberately uses two features intensely and is delighted scores badly. A real false negative. Fixing it needs an "intended deployment scope" attribute on the entitlement that our systems don't capture today.
4. **Usage events are a proxy for value.** We measure activity, not outcomes. Outcome instrumentation — threats blocked, incidents auto-resolved, analyst hours saved — is the correct long-term numerator and is out of scope here.
5. **Commercial model is inferred from public information.** The framework doesn't depend on the specifics; the SKU and packaging details are illustrative.

---

## 9. Roadmap — asserted to derived weights

| Phase | Scope | Effort |
|---|---|---|
| **Now** | PM-assigned 3/2/1 tiers, reviewed by each platform's product team | Shipped |
| **Q+1** | Backtest VRR against 24 months of real renewal and expansion outcomes; measure lift over NRR-at-renewal as an early-warning signal | ~6 weeks, 1 DS + 1 DE |
| **Q+2** | Fit feature weights by regularized regression of feature activity on renewal/expansion; **publish the deltas against the asserted tiers** | ~1 quarter |
| **Q+3** | Quarterly weight review board (Product + CS + Finance); weights become a versioned, auditable artifact | Ongoing |

Publishing the deltas matters. Where the model disagrees with the product team about which features are Core, that disagreement is itself a product finding.

---

## 10. Minimum viable version

If only one quarter of capacity exists: **ship ConsumptionRate and unweighted FeatureCoverage** at `customer × SKU`, on existing telemetry. No weights, no apex, no Value at Risk.

That alone surfaces shelfware and spike-and-drop, which is where the revenue risk concentrates. Feature value tiering is the expensive part — it needs product-org input across ~2,000 features.

---

## 11. Relationship to metrics we already have

| Existing metric | Relationship |
|---|---|
| **NRR / churn rate** | Downstream outcomes. VRR is the leading indicator — it tells you two quarters earlier, at feature level, and it's actionable by a named CSM on a named account. |
| **Acquisition rate** | Upstream. Feeds the Q2/Q3 facts; not a component of the score. |
| **Consumption reporting** | A subset. ConsumptionRate is one of the two VRR factors; reported today without the breadth half, which is why over-consuming accounts look healthy. |
