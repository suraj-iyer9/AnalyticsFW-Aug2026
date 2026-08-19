#!/usr/bin/env python3
"""
Synthetic B2B SaaS dataset generator for the Product Adoption & Value
Realization framework.

Implements section 2 (data model) and section 3 (injected anomalies) of
specs/02_technical_spec.md.

Deterministic: seeded from RANDOM_SEED in .env. Same seed => same dataset,
so downstream test assertions are stable.

Usage:
    python data_generation/generate_dataset.py
Outputs CSVs to data_generation/output/.
"""

from __future__ import annotations

import os
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from faker import Faker

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# ---------------------------------------------------------------- config ---
SEED = int(os.getenv("RANDOM_SEED", 42))
MONTHS_HISTORY = int(os.getenv("MONTHS_HISTORY", 15))
DATA_AS_OF = date(2026, 8, 1)  # last month in the window

N_CUSTOMERS = 100
N_PRODUCTS = 500
N_ENTITLEMENTS_BASE = 480          # + 12 expansions + 8 gap-renewals = 500
N_EXPANSIONS = 12
N_RENEWAL_GAPS = 8                 # B4
N_UNLIMITED = 5                    # B2
N_INTERNAL = 3                     # B6
DUPLICATE_SHARE = 0.02             # B1
UNENTITLED_SHARE = 0.02            # B3
LATE_DATA_FACTOR = 0.40            # B5 — last month is only ~40% loaded
FX = {"USD": 1.00, "EUR": 1.09, "GBP": 1.27}   # B7
FX_SHARE = 0.20

ACCOUNT_OWNERS = ["A. Rivera", "B. Chen", "C. Okafor",
                  "D. Novak", "E. Haddad", "F. Lindqvist"]

COHORT_SHARES = {          # section 3 of the technical spec
    "spike_drop": 0.05,
    "shelfware": 0.10,
    "overage": 0.15,
    "healthy": 0.70,
}

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)

random.seed(SEED)
np.random.seed(SEED)
fake = Faker("en_US")
Faker.seed(SEED)

MONTHS = [
    (DATA_AS_OF - relativedelta(months=MONTHS_HISTORY - 1 - i))
    for i in range(MONTHS_HISTORY)
]
WINDOW_START, WINDOW_END = MONTHS[0], MONTHS[-1]

PLATFORMS = {
    "Network Security (Strata)": ["NGFW", "Advanced Threat Prevention", "Advanced URL Filtering",
                                  "Advanced WildFire", "Advanced DNS Security", "IoT Security"],
    "Prisma SASE": ["Prisma Access", "Prisma SD-WAN", "Prisma Browser",
                    "Enterprise DLP", "SaaS Security", "Autonomous DEM"],
    "Cortex": ["Cortex XSIAM", "Cortex XDR", "Cortex XSOAR", "Cortex Cloud",
               "Attack Surface Management", "Exposure Management"],
    "Prisma AIRS": ["AI Runtime Security", "AI Access Security",
                    "AI Model Scanning", "AI Posture Management"],
}
SKU_TIERS = ["Essentials", "Advanced", "Premium"]

FEATURE_VERBS = ["Policy", "Detection", "Automation", "Reporting", "Inline Analysis",
                 "Posture Assessment", "Threat Hunting", "Alert Triage", "Log Retention",
                 "Anomaly Scoring", "Segmentation", "Data Classification", "Sandboxing",
                 "Risk Scoring", "Playbook Orchestration", "Compliance Mapping",
                 "Identity Correlation", "Traffic Inspection", "Rule Optimisation",
                 "Incident Timeline"]

TIER_WEIGHTS = {"Core": 3, "Differentiator": 2, "Adjacent": 1}


def log(msg: str) -> None:
    print(f"  {msg}")


# ------------------------------------------------------------- customers ---
def build_customers() -> pd.DataFrame:
    cohorts = (
        ["spike_drop"] * round(N_CUSTOMERS * COHORT_SHARES["spike_drop"])
        + ["shelfware"] * round(N_CUSTOMERS * COHORT_SHARES["shelfware"])
        + ["overage"] * round(N_CUSTOMERS * COHORT_SHARES["overage"])
    )
    cohorts += ["healthy"] * (N_CUSTOMERS - len(cohorts))
    random.shuffle(cohorts)

    # B6 — internal/test tenants sitting in production data
    internal_idx = set(random.sample(range(N_CUSTOMERS), N_INTERNAL))

    rows = []
    for i in range(N_CUSTOMERS):
        rows.append(
            {
                "cust_id": f"C{i + 1:04d}",
                "cust_name": fake.unique.company(),
                "region": random.choices(
                    ["AMER", "EMEA", "APAC", "JAPAC"], weights=[0.45, 0.3, 0.17, 0.08]
                )[0],
                "segment": random.choices(
                    ["Enterprise", "Mid-Market"], weights=[0.55, 0.45]
                )[0],
                "industry": random.choice(
                    ["Financial Services", "Healthcare", "Manufacturing", "Retail",
                     "Public Sector", "Technology", "Energy", "Telecom"]
                ),
                "customer_since": fake.date_between(
                    date(2016, 1, 1), date(2025, 1, 1)
                ),
                # GROUND TRUTH — consumed by the test suite only. No pipeline
                # model reads this column; metrics must detect these patterns
                # from behaviour alone.
                "behaviour_cohort": cohorts[i],
                # owner dimension — required to compute Value at Risk Recovered
                # per rep (product spec §7). Without it the comp design is theory.
                "account_owner": ACCOUNT_OWNERS[i % len(ACCOUNT_OWNERS)],
                "is_internal": i in internal_idx,          # B6
            }
        )
    df = pd.DataFrame(rows)
    # internal tenants look obviously fake — that is the point; nobody removes them
    df.loc[df.is_internal, "cust_name"] = [
        f"INTERNAL — {n} Sandbox" for n in ["QA", "Demo", "SE"][: df.is_internal.sum()]
    ]
    return df


# -------------------------------------------------- products and features ---
def build_products() -> pd.DataFrame:
    rows = []
    platform_names = list(PLATFORMS)
    for i in range(N_PRODUCTS):
        platform = random.choices(platform_names, weights=[0.35, 0.25, 0.30, 0.10])[0]
        family = random.choice(PLATFORMS[platform])
        tier = random.choice(SKU_TIERS)
        rows.append(
            {
                "product_id": f"P{i + 1:04d}",
                "product_name": f"{family} — {tier}",
                "product_platform": platform,
                "sku_tier": tier,
                # heterogeneous commercial models on purpose: the framework
                # must handle both credit-burn and seat-licensed SKUs
                "consumption_model": "credits" if platform in ("Cortex", "Prisma AIRS")
                else random.choices(["licensed_units", "credits"], weights=[0.75, 0.25])[0],
                "list_price_per_unit": round(random.uniform(12, 480), 2),
            }
        )
    return pd.DataFrame(rows)


def build_features(products: pd.DataFrame) -> pd.DataFrame:
    rows, fid = [], 0
    for p in products.itertuples():
        n = random.randint(3, 5)
        # every product gets >= 1 Core feature (invariant, tested)
        tiers = ["Core"] + random.choices(
            ["Core", "Differentiator", "Adjacent"], weights=[0.15, 0.4, 0.45], k=n - 1
        )
        for tier in tiers:
            fid += 1
            verb = random.choice(FEATURE_VERBS)
            rows.append(
                {
                    "feature_id": f"F{fid:05d}",
                    "product_id": p.product_id,
                    "feature_name": f"{verb} ({p.product_name.split(' — ')[0]})",
                    "feature_description": (
                        f"{tier} capability providing {verb.lower()} within "
                        f"{p.product_name}."
                    ),
                    "feature_tier": tier,
                    "feature_value_weight": TIER_WEIGHTS[tier],
                }
            )
    return pd.DataFrame(rows)


# ----------------------------------------------------------- entitlements ---
def build_entitlements(customers: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cust_ids = customers.cust_id.tolist()
    prod_ids = products.product_id.tolist()

    # Every customer gets a floor of 3 entitlements, then the remainder is
    # distributed with Enterprise accounts weighted higher. Guaranteeing the
    # floor matters: a customer with no entitlement silently drops out of the
    # cohort population and weakens the anomaly tests.
    seg = dict(zip(customers.cust_id, customers.segment))
    assignments = [c for c in cust_ids for _ in range(3)]
    weights = [2.5 if seg[c] == "Enterprise" else 1.0 for c in cust_ids]
    assignments += random.choices(
        cust_ids, weights=weights, k=N_ENTITLEMENTS_BASE - len(assignments)
    )
    random.shuffle(assignments)

    for i, cust in enumerate(assignments):
        # start anywhere from 6 months before the window to month 5 of it
        offset = random.randint(-6, 5)
        start = WINDOW_START + relativedelta(months=offset)
        end = start + relativedelta(months=12) - timedelta(days=1)
        units = random.choice([10, 25, 50, 100, 250, 500, 1000, 2500])
        ccy = random.choices(list(FX), weights=[1 - FX_SHARE, FX_SHARE * 0.6,
                                                FX_SHARE * 0.4])[0]          # B7
        rows.append(
            {
                "entitlement_id": f"E{i + 1:05d}",
                "cust_id": cust,
                "product_id": random.choice(prod_ids),
                "units_purchased": units,
                # annual entitled consumption capacity
                "licensed_amount": float(units * random.choice([12, 24, 48, 120])),
                "start_date": start,
                "end_date": end,
                "contract_type": random.choices(
                    ["New", "Renewal"], weights=[0.45, 0.55]
                )[0],
                "currency": ccy,                                              # B7
                "fx_rate_to_usd": FX[ccy],                                    # B7
                "is_unlimited": False,
            }
        )

    df = pd.DataFrame(rows)

    # --- B2: unlimited entitlements — no denominator exists -----------------
    # A real commercial construct ("unlimited ingestion"). A consumption rate
    # cannot be computed; the metric must not invent one.
    unl = df.sample(n=N_UNLIMITED, random_state=SEED).index
    df.loc[unl, "is_unlimited"] = True
    df.loc[unl, "licensed_amount"] = np.nan

    # --- B4: renewal gaps — contract lapses, then renews ---------------------
    # Truncate a contract early, then start its replacement 30-60 days later.
    # The gap months must NOT be scored: "no active contract" is a third state,
    # distinct from "active contract, no usage" (= shelfware).
    gap_src = df[(~df.is_unlimited) & (df.start_date <= WINDOW_START)].sample(
        n=N_RENEWAL_GAPS, random_state=SEED + 1
    )
    gap_rows = []
    for j, r in enumerate(gap_src.itertuples()):
        new_end = r.start_date + relativedelta(months=5)
        df.loc[df.entitlement_id == r.entitlement_id, "end_date"] = new_end
        # 60-120 days, not 30-60. A calendar month counts as covered if a
        # contract is active for ANY day of it, so a short gap is invisible at
        # monthly grain. The gap has to span a whole month to be real.
        gap_days = random.randint(60, 120)
        renew_start = new_end + timedelta(days=gap_days)
        gap_rows.append(
            {
                "entitlement_id": f"E8{j + 1:04d}",
                "cust_id": r.cust_id,
                "product_id": r.product_id,
                "units_purchased": r.units_purchased,
                "licensed_amount": r.licensed_amount,
                "start_date": renew_start,
                "end_date": renew_start + relativedelta(months=12) - timedelta(days=1),
                "contract_type": "Renewal",
                "currency": r.currency,
                "fx_rate_to_usd": r.fx_rate_to_usd,
                "is_unlimited": False,
            }
        )
    df = pd.concat([df, pd.DataFrame(gap_rows)], ignore_index=True)

    # --- mid-year expansions: overlapping active entitlement dates ----------
    # A second, LARGER contract for the same customer+product starting mid-term.
    # This is the case a naive denominator double-counts.
    eligible = df[(df.start_date <= WINDOW_START + relativedelta(months=3))
                  & (~df.is_unlimited)]
    picks = eligible.sample(n=min(N_EXPANSIONS, len(eligible)), random_state=SEED)
    exp_rows = []
    for j, r in enumerate(picks.itertuples()):
        exp_start = r.start_date + relativedelta(months=6)
        exp_rows.append(
            {
                "entitlement_id": f"E9{j + 1:04d}",
                "cust_id": r.cust_id,
                "product_id": r.product_id,          # same SKU => real overlap
                "units_purchased": int(r.units_purchased * 2),
                "licensed_amount": float(r.licensed_amount * random.uniform(1.5, 2.5)),
                "start_date": exp_start,
                "end_date": exp_start + relativedelta(months=12) - timedelta(days=1),
                "contract_type": "Expansion",
                "currency": r.currency,
                "fx_rate_to_usd": r.fx_rate_to_usd,
                "is_unlimited": False,
            }
        )
    return pd.concat([df, pd.DataFrame(exp_rows)], ignore_index=True)


# ------------------------------------------------------------ consumption ---
def active_months(start: date, end: date) -> list[date]:
    return [m for m in MONTHS if m >= start.replace(day=1) and m <= end]


def monthly_ratio(cohort: str, idx: int, n: int) -> float:
    """Consumed / monthly-entitled, by behaviour cohort and month index."""
    if cohort == "shelfware":
        return 0.0

    if cohort == "spike_drop":
        # 90% of the ANNUAL entitlement burned across months 1-3, then nothing.
        # Monthly entitled = annual/12, so 30% of annual == 3.6x monthly.
        if idx < 3:
            return random.uniform(3.2, 4.0)
        return 0.0 if random.random() < 0.85 else random.uniform(0.0, 0.03)

    if cohort == "overage":
        ramp = min(1.0, (idx + 1) / 2)
        return round(ramp * random.uniform(1.20, 1.60), 4)

    # healthy: ramp over ~4 months to a stable target, with noise
    target = random.uniform(0.60, 0.95)
    ramp = min(1.0, (idx + 1) / 4)
    return round(max(0.0, target * ramp * random.uniform(0.85, 1.15)), 4)


def build_consumption(entitlements: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    cohort_of = dict(zip(customers.cust_id, customers.behaviour_cohort))
    rows = []
    for e in entitlements.itertuples():
        months = active_months(e.start_date, e.end_date)
        if not months:
            continue
        cohort = cohort_of[e.cust_id]
        # B2 — unlimited contracts still consume; they simply have no denominator.
        # A notional capacity drives generation, but licensed_amount stays NULL.
        unlimited = bool(e.is_unlimited) or pd.isna(e.licensed_amount)
        notional = float(e.units_purchased) * 48.0 if unlimited else float(e.licensed_amount)
        monthly_entitled = notional / 12.0
        for idx, m in enumerate(months):
            ratio = monthly_ratio(cohort, idx, len(months))
            consumed = monthly_entitled * ratio
            # B5 — the final month is only partially loaded when the pipeline runs
            if m == WINDOW_END:
                consumed *= LATE_DATA_FACTOR
            # Real telemetry emits NO ROW when there is no usage — it does not
            # emit a zero. Modelling that honestly is what forces the pipeline's
            # zero-fill to do real work: without it a shelfware account produces
            # NULL, and NULL in this system means "too new to judge" — the exact
            # opposite of the correct conclusion.
            if consumed <= 0:
                continue
            rows.append(
                {
                    "entitlement_id": e.entitlement_id,
                    "cust_id": e.cust_id,
                    "product_id": e.product_id,
                    "month": m,
                    "consumed_units": round(consumed, 2),
                    "licensed_amount_month": (
                        np.nan if unlimited else round(monthly_entitled, 2)
                    ),
                }
            )
    return pd.DataFrame(rows)


# -------------------------------------------------------- feature adoption ---
def build_feature_adoption(
    entitlements: pd.DataFrame, features: pd.DataFrame, customers: pd.DataFrame
) -> pd.DataFrame:
    cohort_of = dict(zip(customers.cust_id, customers.behaviour_cohort))
    feats_by_product = {
        pid: g[["feature_id", "feature_tier"]].to_dict("records")
        for pid, g in features.groupby("product_id")
    }
    rows = []
    for e in entitlements.itertuples():
        months = active_months(e.start_date, e.end_date)
        if not months:
            continue
        cohort = cohort_of[e.cust_id]
        for f in feats_by_product.get(e.product_id, []):
            tier = f["feature_tier"]
            # month index at which this feature becomes active, by cohort
            if cohort == "shelfware":
                onset = None
            elif cohort == "spike_drop":
                onset = 0 if tier == "Core" else None
            elif cohort == "overage":
                # heavy consumers of a NARROW set — high burn, low breadth
                onset = 0 if tier == "Core" else (2 if random.random() < 0.20 else None)
            else:  # healthy
                onset = {
                    "Core": random.randint(0, 1),
                    "Differentiator": random.randint(2, 5) if random.random() < 0.75 else None,
                    "Adjacent": random.randint(4, 8) if random.random() < 0.40 else None,
                }[tier]

            for idx, m in enumerate(months):
                active = False
                if onset is not None and idx >= onset:
                    active = True
                    # spike_drop abandons after month 3
                    if cohort == "spike_drop" and idx >= 3:
                        active = False
                    # healthy accounts occasionally lapse a month
                    elif cohort == "healthy" and random.random() < 0.05:
                        active = False
                # B5 — final month is partially loaded; some activity hasn't landed
                if active and m == WINDOW_END and random.random() > LATE_DATA_FACTOR:
                    active = False
                rows.append(
                    {
                        "entitlement_id": e.entitlement_id,
                        "cust_id": e.cust_id,
                        "product_id": e.product_id,
                        "feature_id": f["feature_id"],
                        "month": m,
                        "is_active": active,
                        "usage_events": int(np.random.gamma(2, 220)) if active else 0,
                        "active_users": int(np.random.gamma(2, 6)) + 1 if active else 0,
                    }
                )
    return pd.DataFrame(rows)


# ------------------------------------------------------ deployment events ---
def build_deployment_events(
    entitlements: pd.DataFrame, customers: pd.DataFrame
) -> pd.DataFrame:
    cohort_of = dict(zip(customers.cust_id, customers.behaviour_cohort))
    rows = []
    for e in entitlements.itertuples():
        cohort = cohort_of[e.cust_id]
        s = e.start_date
        events = {"contract_start": s}
        if cohort != "shelfware":
            events["kickoff"] = s + timedelta(days=random.randint(3, 21))
            events["first_login"] = s + timedelta(days=random.randint(7, 35))
            ttfv = {
                "healthy": random.randint(20, 75),
                "overage": random.randint(10, 40),
                "spike_drop": random.randint(8, 25),
            }[cohort]
            events["first_value"] = s + timedelta(days=ttfv)
            if cohort in ("healthy", "overage"):
                events["core_complete"] = s + timedelta(days=ttfv + random.randint(10, 90))
        else:
            # shelfware: contract signed, nothing ever happened.
            # Some don't even reach kickoff — that absence IS the signal.
            if random.random() < 0.4:
                events["kickoff"] = s + timedelta(days=random.randint(10, 60))
        for etype, edate in events.items():
            rows.append(
                {
                    "entitlement_id": e.entitlement_id,
                    "cust_id": e.cust_id,
                    "product_id": e.product_id,
                    "event_type": etype,
                    "event_date": edate,
                }
            )
    return pd.DataFrame(rows)


# ------------------------------------------------- data-integrity injectors ---
def inject_duplicates(consumption: pd.DataFrame) -> pd.DataFrame:
    """B1 — a pipeline re-run emits the same contract-month twice.

    Dangerous because it makes consumption look HIGHER. Nobody investigates a
    metric that improved, so this survives in production for months.
    """
    dupes = consumption.sample(frac=DUPLICATE_SHARE, random_state=SEED)
    return pd.concat([consumption, dupes], ignore_index=True)


def inject_unentitled_usage(
    adoption: pd.DataFrame, features: pd.DataFrame
) -> pd.DataFrame:
    """B3 — usage recorded against a feature the customer never bought.

    Arises from trial access or a mid-year repackaging. Left unhandled it pushes
    feature coverage above 100%, and a number above target is rarely questioned.
    """
    all_feature_ids = features.feature_id.tolist()
    idx = adoption.sample(frac=UNENTITLED_SHARE, random_state=SEED + 2).index
    foreign = random.choices(all_feature_ids, k=len(idx))
    adoption.loc[idx, "feature_id"] = foreign
    adoption.loc[idx, "is_active"] = True
    return adoption


# -------------------------------------------------------------- validation ---
def validate(tables: dict[str, pd.DataFrame]) -> bool:
    print("\n" + "=" * 68)
    print("VALIDATION — injected anomalies and structural invariants")
    print("=" * 68)

    cust, ent, cons = tables["customers"], tables["entitlements"], tables["consumption_monthly"]
    feats = tables["features"]
    ok = True

    def assert_(label, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  →  {detail}" if detail else ""))

    n = len(cust)
    shares = cust.behaviour_cohort.value_counts(normalize=True)
    assert_("spike_drop share in [3%, 7%]", 0.03 <= shares.get("spike_drop", 0) <= 0.07,
            f"{shares.get('spike_drop', 0):.1%}")
    assert_("shelfware share in [8%, 12%]", 0.08 <= shares.get("shelfware", 0) <= 0.12,
            f"{shares.get('shelfware', 0):.1%}")
    assert_("overage share in [13%, 17%]", 0.13 <= shares.get("overage", 0) <= 0.17,
            f"{shares.get('overage', 0):.1%}")

    # overlapping entitlements
    ovl = 0
    for (_, _), g in ent.groupby(["cust_id", "product_id"]):
        if len(g) < 2:
            continue
        r = g.sort_values("start_date").to_dict("records")
        for a, b in zip(r, r[1:]):
            if b["start_date"] <= a["end_date"]:
                ovl += 1
    assert_("overlapping active entitlements exist", ovl >= 1, f"{ovl} overlapping pairs")

    # ---- Family B: data-integrity injections ----------------------------
    print("  --- Family B (added beyond the brief) ---")

    dup = cons.duplicated(subset=["entitlement_id", "month"]).sum()
    assert_("B1 duplicate consumption rows present", dup > 0, f"{dup} duplicate rows")

    assert_("B2 unlimited entitlements present",
            int(ent.is_unlimited.sum()) == N_UNLIMITED,
            f"{int(ent.is_unlimited.sum())} contracts, licensed_amount is NULL")

    entitled = set(zip(feats.product_id, feats.feature_id))
    adopt = tables["feature_adoption_monthly"]
    bad = ~adopt.apply(lambda r: (r.product_id, r.feature_id) in entitled, axis=1)
    assert_("B3 unentitled feature usage present", bad.sum() > 0,
            f"{bad.sum():,} rows reference a feature outside the SKU")

    gaps = 0
    for (_, _), g in ent.groupby(["cust_id", "product_id"]):
        if len(g) < 2:
            continue
        r = g.sort_values("start_date").to_dict("records")
        for a, b in zip(r, r[1:]):
            if b["start_date"] > a["end_date"] + timedelta(days=1):
                gaps += 1
    assert_("B4 renewal gaps present", gaps >= 1, f"{gaps} gap(s) between contracts")

    last = cons[cons.month == WINDOW_END].consumed_units.sum()
    prev = cons[cons.month == MONTHS[-2]].consumed_units.sum()
    assert_("B5 final month is partially loaded", last < prev * 0.7,
            f"last month is {last / prev:.0%} of prior month")

    assert_("B6 internal accounts present", int(cust.is_internal.sum()) == N_INTERNAL,
            f"{int(cust.is_internal.sum())} internal tenants")

    ccy = ent.currency.value_counts(normalize=True)
    assert_("B7 non-USD contracts present", ccy.get("USD", 1) < 0.95,
            f"{(1 - ccy.get('USD', 1)):.0%} non-USD")

    assert_("account_owner populated", cust.account_owner.notna().all(),
            f"{cust.account_owner.nunique()} owners")

    print("  --- Family A ---")

    # shelfware really is zero
    sw = set(cust[cust.behaviour_cohort == "shelfware"].cust_id)
    assert_("shelfware accounts have zero consumption",
            cons[cons.cust_id.isin(sw)].consumed_units.sum() == 0,
            f"{len(sw)} accounts")

    # overage really exceeds 120%
    ov = set(cust[cust.behaviour_cohort == "overage"].cust_id)
    ratio = cons[cons.cust_id.isin(ov)].groupby("cust_id").apply(
        lambda g: g.consumed_units.sum() / g.licensed_amount_month.sum(), include_groups=False
    )
    assert_("overage accounts consume >120% overall", (ratio > 1.2).mean() > 0.9,
            f"median {ratio.median():.0%}")

    # every product has a Core feature
    core = feats[feats.feature_tier == "Core"].product_id.nunique()
    assert_("every product has >=1 Core feature", core == tables["products"].product_id.nunique(),
            f"{core}/{tables['products'].product_id.nunique()}")

    # history length
    assert_("at least 12 months of history", cons.month.nunique() >= 12,
            f"{cons.month.nunique()} months")

    # referential integrity
    assert_("no orphan entitlements", ent.cust_id.isin(cust.cust_id).all() and
            ent.product_id.isin(tables["products"].product_id).all())
    assert_("no orphan features", feats.product_id.isin(tables["products"].product_id).all())

    print("=" * 68)
    return ok


# -------------------------------------------------------------------- main ---
def main() -> int:
    print("=" * 68)
    print(f"Generating synthetic dataset  (seed={SEED}, "
          f"{MONTHS_HISTORY} months: {WINDOW_START} → {WINDOW_END})")
    print("=" * 68)

    customers = build_customers();               log(f"customers                {len(customers):>7,}")
    products = build_products();                 log(f"products                 {len(products):>7,}")
    features = build_features(products);         log(f"features                 {len(features):>7,}")
    entitlements = build_entitlements(customers, products)
    log(f"entitlements             {len(entitlements):>7,}  "
        f"({(entitlements.contract_type == 'Expansion').sum()} expansions)")
    consumption = build_consumption(entitlements, customers)
    n_before = len(consumption)
    consumption = inject_duplicates(consumption)                       # B1
    log(f"consumption_monthly      {len(consumption):>7,}  "
        f"(+{len(consumption) - n_before} duplicates injected)")
    adoption = build_feature_adoption(entitlements, features, customers)
    adoption = inject_unentitled_usage(adoption, features)             # B3
    log(f"feature_adoption_monthly {len(adoption):>7,}")
    events = build_deployment_events(entitlements, customers)
    log(f"deployment_events        {len(events):>7,}")

    tables = {
        "customers": customers,
        "products": products,
        "features": features,
        "entitlements": entitlements,
        "consumption_monthly": consumption,
        "feature_adoption_monthly": adoption,
        "deployment_events": events,
    }

    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"\n  Wrote {len(tables)} CSVs → {OUT}")

    return 0 if validate(tables) else 1


if __name__ == "__main__":
    raise SystemExit(main())
