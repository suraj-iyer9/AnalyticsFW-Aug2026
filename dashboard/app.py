#!/usr/bin/env python3
"""
Product Adoption & Value Realization — executive dashboard.

Reads the mart tables in BigQuery. Nothing is computed here; every number comes
from the pipeline, so the dashboard and the tests are looking at the same values.

Design rules enforced in this file:
  1. No internal vocabulary on screen. Every label is something a GM would say
     out loud; the technical name lives in the tooltip so it still maps to the spec.
  2. No number without a yardstick. "40%" is meaningless alone - every figure
     carries a comparison or a typical range.
  3. Every chart states what to DO, not what it plots.
  4. The score is never shown alone - both factors sit beside it.
  5. The incomplete period is drawn greyed and labelled, never hidden.

Run:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")
load_dotenv()

PROJECT = os.getenv("GCP_PROJECT_ID")
MART = f"{PROJECT}.{os.getenv('BQ_DATASET_MART')}"
LOCATION = os.getenv("BQ_LOCATION", "US")

# Validated categorical slots 1-3. Assigned in fixed order and never cycled:
# the score is always blue, capacity always orange, features always aqua.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#8a8880"
SURFACE, GRID = "#fcfcfb", "#e6e5e0"
GOOD, WARN, BAD = "#1baf7a", "#eda100", "#e34948"

st.set_page_config(page_title="Product Adoption Framework", layout="wide")


# ------------------------------------------------------------------ data ---
@st.cache_resource
def client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT)


@st.cache_data(ttl=600)
def q(sql: str) -> pd.DataFrame:
    return client().query(sql.format(MART=MART), location=LOCATION).result().to_dataframe()


def money(v: float) -> str:
    if pd.isna(v):
        return "—"
    for unit, div in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(v) >= div:
            return f"${v / div:,.1f}{unit}"
    return f"${v:,.0f}"


def explain(what: str, do: str) -> None:
    """Two lines under every chart: what it shows, and what to do about it."""
    st.caption(f"**What this shows —** {what}")
    st.caption(f"**What to do —** {do}")


def base_layout(fig: go.Figure, height: int = 320, ytitle: str = "") -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=INK_2, size=12), hovermode="x unified",
        legend=dict(orientation="h", y=1.12, x=0, font=dict(color=INK_2)),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title=ytitle,
                     tickfont=dict(color=MUTED))
    return fig


# ------------------------------------------------------------- start here ---
def start_here() -> None:
    with st.expander("**New here? Read this first — 30 seconds**", expanded=True):
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("""
**The question this answers:** a customer pays us $100k a year. Are they
actually using it?

**The score — Value Realization Rate:** the share of what a customer paid for
that they are actually using. Two percentages, multiplied:

> **% of their features they use  ×  % of their capacity they use**

**What a normal score looks like:** most accounts land between **20% and 50%**.
Enterprise customers routinely deploy a fraction of what they buy — so a low
number is the *finding*, not a failing grade. What matters is the direction and
where the money sits.
            """)
        with c2:
            st.markdown("""
**Words used on this page**

| On screen | Means |
|---|---|
| Paying, not using | No usage 90+ days after they signed |
| Used it, then stopped | Heavy use early, then nothing |
| Using more than they bought | Consuming 120%+ — an expansion conversation |
| Too new to score | Under 90 days old; deliberately not scored |
| Weighted by contract size | Big accounts count more, as in the business |
            """)


# ------------------------------------------------------------ trust strip ---
def trust_strip() -> None:
    audit = q("""
        SELECT action, rows_removed FROM `{MART}.pipeline_audit`
        WHERE run_id = (SELECT MAX(run_id) FROM `{MART}.pipeline_audit`)
          AND action != 'model built'
    """)
    latest = q("SELECT MAX(month) AS m FROM `{MART}.mart_exec_summary` "
               "WHERE NOT is_incomplete").m[0]

    def val(action: str) -> int:
        r = audit[audit.action == action]
        return int(abs(r.rows_removed.iloc[0])) if len(r) else 0

    st.caption(
        f"📅 **Numbers below are complete through {latest:%B %Y}.** "
        f"The current month is still loading and is shown greyed. · "
        f"Cleaned before scoring: {val('exclude internal')} internal test accounts "
        f"removed · {val('dedupe')} duplicate rows removed · "
        f"{val('drop unentitled')} usage rows for features the customer never "
        f"bought · full detail in **Data Quality**"
    )


# --------------------------------------------------------------- overview ---
def view_overview() -> None:
    ex = q("SELECT * FROM `{MART}.mart_exec_summary` ORDER BY month")
    done = ex[~ex.is_incomplete]
    last, prev = done.iloc[-1], done.iloc[-2]
    avg = done.vrr_value_weighted.mean()

    st.markdown("### 1 · Where we stand")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Value Realization Rate",
              f"{last.vrr_value_weighted:.0%}",
              f"{last.vrr_value_weighted - prev.vrr_value_weighted:+.1%} vs last month",
              help="Share of contract value being actively used. "
                   "Typical range 20–50%. 12-month average for this portfolio: "
                   f"{avg:.0%}. Technical name: VRR.")
    c2.metric("Contract value not converting",
              money(last.annualized_var_usd),
              f"{1 - last.vrr_value_weighted:.0%} of the book",
              delta_color="off",
              help="Annualized run rate. Assumes this month's behaviour continues "
                   "for twelve. Technical name: Value at Risk.")
    c3.metric("Paying, not using",
              f"{int(last.n_shelfware)}",
              "customer–SKU relationships", delta_color="off",
              help="A customer holding a SKU with zero usage 90+ days after the "
                   "contract started. Counted per customer-SKU pair, not per "
                   "customer — one customer can be healthy on one SKU and dormant "
                   "on another. Technical name: shelfware.")
    c4.metric("Using more than they bought",
              f"{int(last.n_overage)}",
              "customer–SKU relationships", delta_color="off",
              help="Consuming 120%+ of entitlement for 3+ months. Counted per "
                   "customer-SKU pair. Both a growth signal and a contract-sizing "
                   "problem.")

    st.divider()
    st.markdown("### 2 · Why the score is what it is")
    fig = go.Figure()
    for name, col, colour in [
        ("Value Realization Rate", "vrr_value_weighted", BLUE),
        ("% of capacity being used", "consumption_rate", ORANGE),
        ("% of features being used", "feature_coverage", AQUA),
    ]:
        fig.add_trace(go.Scatter(x=done.month, y=done[col], name=name,
                                 mode="lines", line=dict(color=colour, width=2)))
        tail = ex.iloc[-2:]
        fig.add_trace(go.Scatter(x=tail.month, y=tail[col], mode="lines",
                                 line=dict(color=MUTED, width=2, dash="dot"),
                                 showlegend=False, hoverinfo="skip"))
    fig.add_annotation(x=ex.month.iloc[-1], y=1.0, text="still loading",
                       showarrow=False, font=dict(color=MUTED, size=11),
                       yanchor="bottom")
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    st.plotly_chart(base_layout(fig, 340), width="stretch")
    explain(
        "The score, and the two things it is made of. The score is never shown "
        "alone because the same number can mean opposite problems — heavy use of "
        "one feature, or light use of many.",
        "Look at which of the two lines is lower. If capacity is high and features "
        "are low, customers are over-relying on one thing. If features are high and "
        "capacity is low, they set it up and never scaled it.",
    )

    st.divider()
    quadrant_view()

    st.divider()
    feature_depth_portfolio()

    st.divider()
    st.markdown("### 5 · Where the money is")
    left, right = st.columns(2)

    with left:
        st.markdown("**Realized vs. not converting, per month**")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=done.month, y=done.realized_value_usd,
                             name="Being used", marker_color=AQUA,
                             marker_line=dict(color=SURFACE, width=2),
                             text=[money(v) for v in done.realized_value_usd],
                             textposition="inside", insidetextanchor="middle",
                             textfont=dict(color="#ffffff", size=10)))
        fig.add_trace(go.Bar(x=done.month, y=done.value_at_risk_usd,
                             name="Not converting", marker_color=ORANGE,
                             marker_line=dict(color=SURFACE, width=2),
                             text=[money(v) for v in done.value_at_risk_usd],
                             textposition="inside", insidetextanchor="middle",
                             textfont=dict(color="#ffffff", size=10)))
        fig.update_layout(barmode="stack", bargap=0.35,
                          uniformtext_minsize=8, uniformtext_mode="hide")
        st.plotly_chart(base_layout(fig, 300, "USD per month"), width="stretch")
        explain("Every dollar of contract value, split into the part customers "
                "are using and the part they are not.",
                "The orange band is the addressable pool. It is where deployment "
                "investment pays back.")

    with right:
        st.markdown("**Which segment carries the risk**")
        seg = q("""
            SELECT segment, SUM(value_at_risk_usd) * 12 AS var_usd,
                   COUNT(*) AS customers
            FROM `{MART}.mart_customer_adoption`
            WHERE month = (SELECT MAX(month) FROM `{MART}.mart_customer_adoption`
                           WHERE NOT is_incomplete)
            GROUP BY segment ORDER BY var_usd DESC
        """)
        fig = go.Figure(go.Bar(
            x=seg.var_usd, y=seg.segment, orientation="h", marker_color=BLUE,
            text=[f"{money(v)}  ·  {c} accounts" for v, c in zip(seg.var_usd, seg.customers)],
            textposition="outside", textfont=dict(color=INK_2)))
        fig.update_layout(bargap=0.45)
        st.plotly_chart(base_layout(fig, 300), width="stretch")
        explain("The same dollars, cut by customer segment. Percentages cannot be "
                "added across customers; dollars can.",
                "Fund the segment with the largest pool first — that is a "
                "resourcing decision the score alone cannot support.")

    st.divider()
    st.markdown("### Are big accounts doing better or worse than small ones?")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=done.month, y=done.vrr_value_weighted,
                             name="Weighted by contract size", mode="lines",
                             line=dict(color=BLUE, width=2)))
    fig.add_trace(go.Scatter(x=done.month, y=done.vrr_unweighted,
                             name="Every account counts equally", mode="lines",
                             line=dict(color=ORANGE, width=2, dash="dash")))
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    st.plotly_chart(base_layout(fig, 260), width="stretch")
    gap = last.vrr_value_weighted - last.vrr_unweighted
    explain(
        "Two ways of averaging the same score. Weighted reflects how the "
        "*business* is doing; unweighted reflects how *customers* are doing.",
        ("Weighted is **below** unweighted, so our larger contracts are adopting "
         "worse than our smaller ones — the opposite of the usual pattern, and "
         "worth a root-cause look."
         if gap < -0.01 else
         "Weighted is **above** unweighted, so adoption success is concentrated in "
         "large accounts and the smaller-account motion needs attention."
         if gap > 0.01 else
         "The two track closely, so adoption performance is even across account "
         "sizes — the problem is portfolio-wide, not concentrated."),
    )


# ---------------------------------------------------------- the 2x2 view ---
# Four quadrants, four owners, four plays.
#
# Position is the PRIMARY encoding here - colour is redundant reinforcement, and
# each quadrant carries a written label. That matters because these are STATUS
# colours (good / warning / serious / critical), which are reserved for state and
# must never be the only thing distinguishing one group from another.
QUADRANTS = [
    # key, label, the play, who owns it, colour
    ("value",   "Realizing value",        "Expansion conversation",              "Sales",           GOOD),
    ("scaled",  "Set up, never scaled",   "Enablement — why hasn't volume grown?", "Customer Success", WARN),
    ("hot",     "Running hot on one thing", "They'll hit the cap and renegotiate on price", "Sales + Product", ORANGE),
    ("stalled", "Not started",            "Deployment intervention — churn risk", "CS leadership",   BAD),
]
DEFAULT_SPLIT = 0.5   # a default, not a decree — see the slider below


def quadrant_view() -> None:
    st.markdown("### 3 · The same score, four completely different problems")
    st.caption("Every account, plotted by the two things the score is made of. "
               "Bubble size is contract value.")

    # The cut-off is a dial, not a decree. Nobody has to defend "why 50%" - move
    # it and watch the boxes repopulate. It also makes the shape of the portfolio
    # visible: if accounts only redistribute at a high threshold, the book is
    # bimodal rather than evenly spread.
    # Held as whole percent (30-90) rather than a 0-1 fraction: a "%.0f%%"
    # format string applied to 0.5 renders as "0%", which is what the first
    # version did. Store what you display, convert once.
    SPLIT = st.slider(
        "Where does “high” start?", min_value=30, max_value=90,
        value=int(DEFAULT_SPLIT * 100), step=5, format="%d%%", key="quad_split",
        help="The line between high and low on both axes. Defaults to 50%. "
             "Raise it to separate the merely-adequate from the genuinely healthy.") / 100.0

    df = q("""
        SELECT cust_name, segment, account_owner, feature_coverage,
               consumption_rate, vrr_value_weighted AS vrr,
               licensed_value_usd * 12 AS book_usd,
               value_at_risk_usd  * 12 AS var_usd
        FROM `{MART}.mart_customer_adoption`
        WHERE month = (SELECT MAX(month) FROM `{MART}.mart_customer_adoption`
                       WHERE NOT is_incomplete)
          AND feature_coverage IS NOT NULL AND consumption_rate IS NOT NULL
    """)
    if not len(df):
        st.info("No scored accounts in the latest complete month.")
        return

    def bucket(r) -> str:
        hi_f, hi_c = r.feature_coverage >= SPLIT, r.consumption_rate >= SPLIT
        return ("value" if hi_f and hi_c else
                "scaled" if hi_f else
                "hot" if hi_c else "stalled")

    df["quadrant"] = df.apply(bucket, axis=1)
    size_ref = max(df.book_usd.max() / 900.0, 1e-9)

    fig = go.Figure()
    # quadrant tints, very light — orientation, not decoration
    for x0, x1, y0, y1, colour in [
        (SPLIT, 1.02, SPLIT, 1.02, GOOD), (0, SPLIT, SPLIT, 1.02, WARN),
        (SPLIT, 1.02, 0, SPLIT, ORANGE), (0, SPLIT, 0, SPLIT, BAD),
    ]:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=colour, opacity=0.05, line_width=0, layer="below")

    for key, label, play, owner, colour in QUADRANTS:
        sub = df[df.quadrant == key]
        if not len(sub):
            continue
        fig.add_trace(go.Scatter(
            x=sub.consumption_rate, y=sub.feature_coverage, mode="markers",
            name=f"{label}  ({len(sub)})",
            marker=dict(size=sub.book_usd / size_ref, sizemode="area", sizemin=8,
                        color=colour, opacity=0.75,
                        line=dict(color=SURFACE, width=2)),
            customdata=sub[["cust_name", "vrr", "var_usd", "account_owner"]],
            hovertemplate=("<b>%{customdata[0]}</b><br>"
                           "Capacity used: %{x:.0%}<br>"
                           "Features used: %{y:.0%}<br>"
                           "Score: %{customdata[1]:.0%}<br>"
                           "Not converting: $%{customdata[2]:,.0f}/yr<br>"
                           "Owner: %{customdata[3]}<extra></extra>")))

    fig.add_vline(x=SPLIT, line_width=1, line_color=MUTED, line_dash="dot")
    fig.add_hline(y=SPLIT, line_width=1, line_color=MUTED, line_dash="dot")
    for x, y, xa, ya, text in [
        (1.0, 1.0, "right", "top", "REALIZING VALUE"),
        (0.02, 1.0, "left", "top", "SET UP, NEVER SCALED"),
        (1.0, 0.02, "right", "bottom", "RUNNING HOT ON ONE THING"),
        (0.02, 0.02, "left", "bottom", "NOT STARTED"),
    ]:
        fig.add_annotation(x=x, y=y, text=text, showarrow=False,
                           xanchor=xa, yanchor=ya,
                           font=dict(color=MUTED, size=11))
    fig.update_xaxes(range=[0, 1.03], tickformat=".0%",
                     title="% of capacity being used →")
    fig.update_yaxes(range=[0, 1.03], tickformat=".0%",
                     title="% of features being used →")
    fig = base_layout(fig, 520)
    fig.update_layout(hovermode="closest")   # per-point, not grouped by x
    st.plotly_chart(fig, width="stretch")

    rows = []
    for key, label, play, owner, _ in QUADRANTS:
        sub = df[df.quadrant == key]
        rows.append({"Where they sit": label, "Accounts": len(sub),
                     "Not converting / yr": money(sub.var_usd.sum()),
                     "What to do": play, "Who owns it": owner})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    explain(
        "The two halves of the score, plotted against each other. An account at "
        "26% could be in any of these four boxes — and each one is a different "
        "problem with a different owner.",
        "Work the boxes, not the score. Bottom-left is a rescue. Bottom-right is a "
        "pricing conversation waiting to happen. Top-left is an enablement gap. "
        "Top-right is where expansion comes from.",
    )



# ------------------------------------------------- how deep does use go? ---
# A raw count of features used ignores the weighting - three Adjacent features
# is not the same as the one Core feature the SKU was bought for. So every bar
# is split by whether the Core feature is among the ones in use. The chart then
# says two things at once: how MUCH of the SKU they touch, and whether they
# touch the part that matters.
#
# De-duplicated to cust x product x feature first: a customer holding two
# overlapping contracts on the same SKU must not have their features counted twice.
DEPTH_SQL = """
WITH f AS (
  SELECT cust_id, product_id, feature_id,
         LOGICAL_OR(is_active)   AS is_active,
         ANY_VALUE(feature_tier) AS feature_tier
  FROM `{MART}.stg_feature_activity`
  WHERE month = (SELECT MAX(month) FROM `{MART}.mart_exec_summary`
                 WHERE NOT is_incomplete)
    {FILTER}
  GROUP BY cust_id, product_id, feature_id
),
per_sku AS (
  SELECT cust_id, product_id,
         COUNTIF(is_active) AS features_used,
         COUNT(*)           AS features_entitled,
         LOGICAL_OR(is_active AND feature_tier = 'Core') AS uses_core
  FROM f GROUP BY cust_id, product_id
)
SELECT features_used, uses_core, COUNT(*) AS n
FROM per_sku GROUP BY features_used, uses_core ORDER BY features_used
"""


def depth_chart(df: pd.DataFrame, height: int = 320) -> go.Figure:
    used = sorted(df.features_used.unique())
    labels = [f"{u} feature" if u == 1 else f"{u} features" for u in used]
    with_core = [int(df[(df.features_used == u) & (df.uses_core)].n.sum()) for u in used]
    no_core = [int(df[(df.features_used == u) & (~df.uses_core)].n.sum()) for u in used]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=with_core, name="Includes the Core feature",
                         marker_color=BLUE, marker_line=dict(color=SURFACE, width=2),
                         text=[v or "" for v in with_core], textposition="inside",
                         textfont=dict(color="#ffffff", size=11)))
    fig.add_trace(go.Bar(x=labels, y=no_core, name="No Core feature in use",
                         marker_color=ORANGE, marker_line=dict(color=SURFACE, width=2),
                         text=[v or "" for v in no_core], textposition="inside",
                         textfont=dict(color="#ffffff", size=11)))
    fig.update_layout(barmode="stack", bargap=0.35,
                      uniformtext_minsize=9, uniformtext_mode="hide")
    return base_layout(fig, height, "Customer–SKU relationships")


def feature_depth_portfolio() -> None:
    st.markdown("### 4 · How much of a SKU do customers actually touch?")
    df = q(DEPTH_SQL.replace("{FILTER}", ""))
    if not len(df):
        return
    total = df.n.sum()
    shallow = df[df.features_used <= 1].n.sum()
    no_core = df[~df.uses_core].n.sum()

    a, b, c = st.columns(3)
    a.metric("Use one feature or none", f"{shallow / total:.0%}",
             f"{int(shallow)} of {int(total)} relationships", delta_color="off")
    b.metric("Use no Core feature at all", f"{no_core / total:.0%}",
             "paying for the reason, using something else", delta_color="off")
    c.metric("Use every feature they bought",
             f"{df[df.features_used == df.features_used.max()].n.sum() / total:.0%}",
             "fully deployed", delta_color="off")

    st.plotly_chart(depth_chart(df, 340), width="stretch")
    explain(
        "Every customer–SKU relationship, grouped by how many features are in "
        "use. Blue means the Core feature — the reason the SKU gets bought — is "
        "among them. Orange means it is not.",
        "Look for the cliff. If most relationships stack up at one feature, that "
        "is not a hundred separate customer problems — it is one onboarding or "
        "packaging problem, and fixing it once lifts every account on that SKU.",
    )


# -------------------------------------------------------------- customers ---
STATUS_SQL = """
    CASE
      WHEN skus_deploying = skus_held           THEN 'Too new to score'
      WHEN skus_shelfware > 0                   THEN 'Paying, not using'
      WHEN skus_spike_drop > 0                  THEN 'Used it, then stopped'
      WHEN skus_overage > 0                     THEN 'Using more than they bought'
      WHEN vrr_value_weighted >= 0.5            THEN 'Healthy'
      WHEN vrr_value_weighted >= 0.25           THEN 'Partly deployed'
      ELSE 'Barely deployed'
    END
"""


def view_customers() -> None:
    months = q("SELECT DISTINCT month FROM `{MART}.mart_customer_adoption` "
               "WHERE NOT is_incomplete ORDER BY month DESC")
    f1, f2, f3 = st.columns([2, 2, 3])
    month = f1.selectbox("Month", months.month, key="cust_month",
                         format_func=lambda d: f"{d:%b %Y}")
    seg = f2.selectbox("Segment", ["All", "Enterprise", "Mid-Market"], key="cust_segment")
    only_risk = f3.checkbox("Only accounts needing attention", value=False,
                            key="cust_only_risk")

    df = q(f"""
        SELECT cust_name, {STATUS_SQL} AS status, segment, region, account_owner,
               vrr_value_weighted AS vrr, consumption_rate, feature_coverage,
               licensed_value_usd * 12 AS book_usd,
               value_at_risk_usd   * 12 AS var_usd, skus_held
        FROM `{{MART}}.mart_customer_adoption`
        WHERE month = DATE('{month}')
        ORDER BY var_usd DESC
    """)
    if seg != "All":
        df = df[df.segment == seg]
    if only_risk:
        df = df[~df.status.isin(["Healthy", "Too new to score"])]

    portfolio_vrr = df.vrr.mean()
    st.markdown(
        f"**{len(df)} accounts · {money(df.var_usd.sum())} of contract value not "
        f"converting · average score {portfolio_vrr:.0%}.** "
        "Sorted by dollars at stake, largest first — the top of this list is "
        "where a day of CSM time returns the most."
    )

    st.dataframe(
        df.assign(vrr=(df.vrr * 100).round(0),
                  consumption_rate=(df.consumption_rate * 100).round(0),
                  feature_coverage=(df.feature_coverage * 100).round(0)),
        width="stretch", hide_index=True,
        column_config={
            "cust_name": "Customer",
            "status": st.column_config.TextColumn("Status", help="Plain-language "
                                                  "summary of this account's pattern"),
            "account_owner": "Owner",
            "vrr": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d%%",
                help="Value Realization Rate — % of spend being used. "
                     "Typical range 20–50%."),
            "consumption_rate": st.column_config.NumberColumn(
                "Capacity used", format="%d%%",
                help="Of the credits or seats they bought, how much is in use"),
            "feature_coverage": st.column_config.NumberColumn(
                "Features used", format="%d%%",
                help="Weighted: the features that matter count for more"),
            "book_usd": st.column_config.NumberColumn("Contract value / yr",
                                                      format="$%.0f"),
            "var_usd": st.column_config.NumberColumn("Not converting / yr",
                                                     format="$%.0f"),
            "skus_held": "SKUs",
        },
    )

    st.divider()
    st.markdown("### What would you actually do about one of these accounts?")
    if not len(df):
        return
    who = st.selectbox("Pick a customer", df.cust_name.tolist(), key="cust_drill")
    row = df[df.cust_name == who].iloc[0]

    a, b, c = st.columns(3)
    a.metric("Score", f"{row.vrr:.0%}",
             f"{row.vrr - portfolio_vrr:+.0%} vs portfolio", delta_color="off")
    b.metric("Capacity used", f"{row.consumption_rate:.0%}")
    c.metric("Features used", f"{row.feature_coverage:.0%}")

    gaps = q(f"""
        SELECT a.feature_name, a.feature_tier, f.product_name
        FROM `{{MART}}.stg_feature_activity` a
        JOIN (SELECT DISTINCT product_id, product_name
              FROM `{{MART}}.stg_entitlements`) f USING (product_id)
        WHERE a.cust_id = (SELECT cust_id FROM `{{MART}}.stg_customers`
                           WHERE cust_name = '{who.replace("'", "''")}')
          AND a.month = DATE('{month}') AND NOT a.is_active
        ORDER BY a.feature_value_weight DESC LIMIT 40
    """)
    core = gaps[gaps.feature_tier == "Core"]
    if len(gaps):
        st.warning(
            f"**{who} is paying for {len(gaps)} features they did not use this "
            f"month — {len(core)} of them are the reason the SKU was bought.** "
            f"Roughly {money(row.var_usd)} a year of contract value sits behind "
            "this list."
        )
        st.dataframe(
            gaps.rename(columns={"feature_name": "Unused feature",
                                 "feature_tier": "Importance",
                                 "product_name": "In which SKU"}),
            width="stretch", hide_index=True)
        st.caption("**Importance** — *Core* is the reason they bought it, "
                   "*Differentiator* is why us over a competitor, "
                   "*Adjacent* is nice to have.")
    else:
        st.success(f"{who} is using every feature they are entitled to this month.")


# --------------------------------------------------------------- products ---
def view_products() -> None:
    months = q("SELECT DISTINCT month FROM `{MART}.mart_product_adoption` "
               "WHERE NOT is_incomplete ORDER BY month DESC")
    month = st.selectbox("Month", months.month, key="prod_month",
                         format_func=lambda d: f"{d:%b %Y}")

    plat = q(f"""
        SELECT product_platform,
               SUM(licensed_value_usd) * 12 AS book_usd,
               SUM(value_at_risk_usd)  * 12 AS var_usd,
               SAFE_DIVIDE(SUM(vrr_value_weighted * licensed_value_usd),
                           SUM(licensed_value_usd)) AS vrr
        FROM `{{MART}}.mart_product_adoption`
        WHERE month = DATE('{month}')
        GROUP BY product_platform ORDER BY var_usd DESC
    """)
    worst = plat.iloc[0]
    st.markdown(
        f"**{worst.product_platform} carries the most unconverted value — "
        f"{money(worst.var_usd)} a year, at a {worst.vrr:.0%} score.** "
        "Platform totals below, then the SKUs inside them."
    )

    fig = go.Figure(go.Bar(
        x=plat.var_usd, y=plat.product_platform, orientation="h",
        marker_color=ORANGE,
        text=[f"{money(v)}  ·  score {r:.0%}" for v, r in zip(plat.var_usd, plat.vrr)],
        textposition="outside", textfont=dict(color=INK_2)))
    fig.update_layout(bargap=0.4)
    st.plotly_chart(base_layout(fig, 300), width="stretch")
    explain("Contract value not converting, by platform, with each platform's score.",
            "A large bar with a high score is simply a big platform. A large bar "
            "with a low score is a deployment problem worth funding.")

    st.divider()
    st.markdown("### Which SKUs are underperforming")
    sku = q(f"""
        SELECT product_name, product_platform, sku_tier, customers,
               vrr_value_weighted AS vrr, consumption_rate, feature_coverage,
               licensed_value_usd * 12 AS book_usd,
               value_at_risk_usd  * 12 AS var_usd
        FROM `{{MART}}.mart_product_adoption`
        WHERE month = DATE('{month}')
        ORDER BY var_usd DESC LIMIT 60
    """)
    st.caption("Top 60 SKUs by dollars not converting.")
    st.dataframe(
        sku.assign(vrr=(sku.vrr * 100).round(0),
                   consumption_rate=(sku.consumption_rate * 100).round(0),
                   feature_coverage=(sku.feature_coverage * 100).round(0)),
        width="stretch", hide_index=True,
        column_config={
            "product_name": "SKU", "product_platform": "Platform",
            "sku_tier": "Tier", "customers": "Customers",
            "vrr": st.column_config.ProgressColumn("Score", min_value=0,
                                                   max_value=100, format="%d%%"),
            "consumption_rate": st.column_config.NumberColumn("Capacity used",
                                                              format="%d%%"),
            "feature_coverage": st.column_config.NumberColumn("Features used",
                                                              format="%d%%"),
            "book_usd": st.column_config.NumberColumn("Contract value / yr",
                                                      format="$%.0f"),
            "var_usd": st.column_config.NumberColumn("Not converting / yr",
                                                     format="$%.0f"),
        })

    st.divider()
    st.markdown("### Inside one SKU — which features get used")
    if not len(sku):
        return
    chosen = st.selectbox("Pick a SKU", sku.product_name.tolist(), key="prod_sku")
    feat = q(f"""
        SELECT feature_name, feature_tier, customers_entitled, customers_active,
               adoption_rate
        FROM `{{MART}}.mart_feature_adoption`
        WHERE month = DATE('{month}')
          AND product_id IN (SELECT product_id FROM `{{MART}}.stg_entitlements`
                             WHERE product_name = '{chosen.replace("'", "''")}')
        ORDER BY feature_value_weight DESC, adoption_rate ASC
    """)
    if not len(feat):
        return
    colours = {"Core": BLUE, "Differentiator": ORANGE, "Adjacent": AQUA}
    fig = go.Figure()
    for tier in ["Core", "Differentiator", "Adjacent"]:
        sub = feat[feat.feature_tier == tier]
        if len(sub):
            fig.add_trace(go.Bar(
                x=sub.adoption_rate, y=sub.feature_name, orientation="h",
                name=tier, marker_color=colours[tier],
                marker_line=dict(color=SURFACE, width=2),
                text=[f"{v:.0%}" for v in sub.adoption_rate],
                textposition="outside", textfont=dict(color=INK_2, size=11)))
    fig.update_xaxes(range=[0, 1.15], tickformat=".0%")
    fig.update_layout(bargap=0.35)
    st.plotly_chart(base_layout(fig, 60 + 26 * len(feat)), width="stretch")
    explain("Of the customers entitled to each feature, how many actually used it "
            "this month. Blue features are the reason the SKU gets bought.",
            "A blue bar with low adoption is a packaging or onboarding failure, "
            "not a customer failure. Fix it once and it lifts every account "
            "holding this SKU.")

    st.markdown("**How many of this SKU's features does each customer use?**")
    depth = q(DEPTH_SQL.replace(
        "{FILTER}",
        f"""AND product_id IN (SELECT product_id FROM `{{MART}}.stg_entitlements`
                               WHERE product_name = '{chosen.replace("'", "''")}')"""))
    if len(depth):
        st.plotly_chart(depth_chart(depth, 300), width="stretch")
        shallow = depth[depth.features_used <= 1].n.sum() / depth.n.sum()
        st.caption(f"**{shallow:.0%} of customers on this SKU use one feature or "
                   "none.** A concentration at the left is a deployment problem "
                   "with this SKU, not with those customers.")


# ----------------------------------------------------------------- owners ---
def view_owners() -> None:
    st.markdown("### Paying people on this metric, without it being gamed")
    st.info(
        "**Do not compensate on the score itself.** A rep inherits their accounts — "
        "someone handed a healthy book would win by doing nothing.\n\n"
        "**Compensate on the dollars they move.** *Value Recovered* is how much "
        "contract value shifted from *not converting* to *being used* in a quarter, "
        "across that owner's accounts. It is measured in dollars, so it sums and "
        "compares fairly, and it can only go up if customers genuinely use more.\n\n"
        "**It can be negative.** A book that goes backwards loses credit — "
        "otherwise declining accounts become invisible."
    )

    rec = q("""
        SELECT account_owner, quarter, accounts, opening_var_usd, closing_var_usd,
               value_recovered_usd, quota_usd, quota_attainment
        FROM `{MART}.mart_owner_recovery` ORDER BY quarter, account_owner
    """)
    if not len(rec):
        st.warning("No complete quarters yet.")
        return

    latest = rec[rec.quarter == rec.quarter.max()].sort_values("value_recovered_usd")
    fig = go.Figure(go.Bar(
        x=latest.value_recovered_usd, y=latest.account_owner, orientation="h",
        marker_color=[GOOD if v >= 0 else BAD for v in latest.value_recovered_usd],
        text=[f"{money(v)}  ·  {a:.0%} of target"
              for v, a in zip(latest.value_recovered_usd, latest.quota_attainment)],
        textposition="outside", textfont=dict(color=INK_2)))
    fig.add_vline(x=0, line_width=1, line_color=MUTED)
    fig.update_layout(bargap=0.4)
    st.plotly_chart(base_layout(fig, 300), width="stretch")
    explain(
        f"Dollars moved out of *not converting* during the quarter beginning "
        f"{rec.quarter.max():%b %Y}. Green recovered value; red went backwards.",
        "Target is 15% of the owner's opening at-risk book — a placeholder that "
        "needs a year of history to calibrate. Year one should be set soft.",
    )

    st.caption("Only complete quarters appear. A quarter still loading would "
               "understate everyone and then silently correct upward — unacceptable "
               "for anything attached to pay.")
    st.dataframe(rec, width="stretch", hide_index=True, column_config={
        "account_owner": "Owner", "quarter": "Quarter", "accounts": "Accounts",
        "opening_var_usd": st.column_config.NumberColumn("Not converting, start",
                                                         format="$%.0f"),
        "closing_var_usd": st.column_config.NumberColumn("Not converting, end",
                                                         format="$%.0f"),
        "value_recovered_usd": st.column_config.NumberColumn("Value recovered",
                                                             format="$%.0f"),
        "quota_usd": st.column_config.NumberColumn("Target", format="$%.0f"),
        "quota_attainment": st.column_config.NumberColumn("% of target",
                                                          format="%.0f%%"),
    })


# --------------------------------------------------------- data quality ----
def view_quality() -> None:
    st.markdown("### Can I trust these numbers?")
    runs = q("SELECT DISTINCT run_id, run_ts FROM `{MART}.pipeline_audit` "
             "ORDER BY run_id DESC LIMIT 20")
    run = st.selectbox("Pipeline run", runs.run_id, key="dq_run",
                       format_func=lambda r: f"{runs[runs.run_id == r].run_ts.iloc[0]:%d %b %Y, %H:%M} UTC")

    audit = q(f"""
        SELECT layer, model, action, rows_in, rows_out, rows_removed, note
        FROM `{{MART}}.pipeline_audit`
        WHERE run_id = '{run}' AND action != 'model built' ORDER BY layer, model
    """)

    def val(action: str) -> int:
        r = audit[audit.action == action]
        return int(abs(r.rows_removed.iloc[0])) if len(r) else 0

    st.info(
        f"**In plain English, this run did the following.** It started from the raw "
        f"usage records and removed **{val('dedupe')} duplicate rows** left behind by "
        f"a repeated load. It excluded **{val('exclude internal')} internal test "
        f"accounts** that sit in the source system and would otherwise distort every "
        f"portfolio number. It discarded **{val('drop unentitled')} usage records "
        f"pointing at features the customer never bought**, which would have pushed "
        f"feature adoption above 100%.\n\n"
        f"It then found **{val('zero-fill')} months where a customer had an active "
        f"contract and no usage record at all**, and counted those as **zero rather "
        f"than unknown** — this is the single most important step on the page, "
        f"because a missing row would otherwise be read as *'too new to judge'* and "
        f"the customers most at risk would be the ones we were told to leave alone.\n\n"
        f"Finally it marked **{val('mark incomplete')} rows in the current month as "
        f"still loading**, and excluded **{val('exclude gap months')} months where "
        f"the customer had no active contract at all** — a lapsed renewal is not the "
        f"same as an unused product."
    )

    st.markdown("**Every row this run dropped, added, or flagged**")
    st.dataframe(audit, width="stretch", hide_index=True, column_config={
        "layer": "Stage", "model": "Step", "action": "Action",
        "rows_in": "Rows in", "rows_out": "Rows out",
        "rows_removed": "Rows affected", "note": "Why",
    })

    st.markdown("**Tables rebuilt in this run**")
    built = q(f"""
        SELECT layer, model, rows_out AS row_count, note AS runtime
        FROM `{{MART}}.pipeline_audit`
        WHERE run_id = '{run}' AND action = 'model built' ORDER BY model
    """)
    st.dataframe(built, width="stretch", hide_index=True, column_config={
        "layer": "Stage", "model": "Table", "row_count": "Rows", "runtime": "Runtime",
    })
    st.caption("This log is appended on every run, so if a number changes between "
               "runs you can see which step changed it.")


# ------------------------------------------------------------------- main ---
st.title("Product Adoption & Value Realization")
st.markdown("##### Is what customers bought actually being used — and what is "
            "the gap worth?")
start_here()
trust_strip()


def render(fn, label: str) -> None:
    """One failing tab must not take down the other four during a live demo."""
    try:
        fn()
    except Exception as e:
        st.error(f"**{label} is unavailable.** {type(e).__name__}: "
                 f"{str(e).splitlines()[0][:200]}")
        st.caption("The other tabs are unaffected.")


tabs = st.tabs([
    "Overview — how are we doing?",
    "Customers — who needs attention?",
    "Products — which SKUs are failing?",
    "Owners — who's recovering value?",
    "Data Quality — can I trust this?",
])
for tab, (fn, label) in zip(tabs, [
    (view_overview, "Overview"), (view_customers, "Customers"),
    (view_products, "Products"), (view_owners, "Owners"),
    (view_quality, "Data Quality"),
]):
    with tab:
        render(fn, label)
