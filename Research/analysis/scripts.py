"""
scripts.py — analysis helpers for regression_score.ipynb.

Functions:
  load_recall_records()          → list[dict]
  compute_domain_difficulty()    → dict[domain, dict]
  build_fidelity_matrix(records) → list[dict]   (panel rows)
  run_regression(panel, diff)    → (dict[name→OLS], DataFrame)

  modelwise_recall_all(panel)    → DataFrame  (model × aggregate)
  modelwise_recall_by_domain(p)  → DataFrame  (model × domain pivot)
  modelwise_brier_all(panel)     → DataFrame  (model × aggregate)
  modelwise_brier_by_domain(p)   → DataFrame  (model × domain pivot)

  plot_recall_bar(df, ax)
  plot_brier_bar(df, ax)
  plot_recall_heatmap(pivot, ax)
  plot_brier_heatmap(pivot, ax)
  plot_regression_scatter(reg_df, ax)
  plot_regression_coef(results, ax)
"""

import glob
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

# matplotlib / seaborn are imported lazily inside plot functions so that
# data-loading and regression work even if those packages are not installed.
def _plt():
    import matplotlib.pyplot as _plt
    return _plt

def _sns():
    import seaborn as _sns
    return _sns

RESEARCH_DIR = Path(__file__).parent.parent

DOMAINS = [
    "ClimateMarkets",
    "CommoditiesMarkets",
    "CompaniesMarkets",
    "EconomicsMarkets",
    "ElectionsMarkets",
    "EntertainmentMarkets",
    "FinancialsMarkets",
    "PoliticsMarkets",
    "ScienceTechnologyMarkets",
]

SHORT_DOMAIN = {d: d.replace("Markets", "") for d in DOMAINS}

MODEL_DISPLAY = {
    "claude-opus-4-7_1000":    "Claude Opus 4.7",
    "claude-sonnet-4-6_1000":  "Claude Sonnet 4.6",
    "gemini-3-flash-preview":  "Gemini 3 Flash",
    "gemini-3.1-pro-preview":  "Gemini 3.1 Pro",
    "gpt-5-4":                 "GPT-5.4",
    "gpt-5-5":                 "GPT-5.5",
}

PALETTE = {
    "Claude Opus 4.7":    "#7B61FF",
    "Claude Sonnet 4.6":  "#B39DDB",
    "Gemini 3 Flash":     "#4285F4",
    "Gemini 3.1 Pro":     "#34A853",
    "GPT-5.4":            "#FF6D00",
    "GPT-5.5":            "#FF9E40",
}


def _display(model_id: str) -> str:
    return MODEL_DISPLAY.get(model_id, model_id)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_recall_records() -> list:
    """Load graded recall JSON files; returns one dict per market-model pair."""
    records = []
    for domain in DOMAINS:
        recall_dir = RESEARCH_DIR / domain / "recall"
        for path in sorted(recall_dir.glob("*.json")):
            model = path.stem.replace("_recall", "")
            try:
                items = json.loads(path.read_text())
            except Exception as e:
                print(f"[WARN] {path}: {e}")
                continue
            for item in items:
                fc = item.get("forecast") or {}
                ra = fc.get("recall_assessment") or {}
                probs = fc.get("probabilities") or {}
                p_yes = probs.get("Yes")
                records.append({
                    "model":              model,
                    "domain":             domain,
                    "condition_id":       item.get("condition_id", ""),
                    "question_text":      item.get("title", ""),
                    "actual_resolution":  item.get("actual_resolution"),
                    "recall_score":       ra.get("recall_score"),
                    "p_yes":              p_yes,
                    "recalled_outcome":   ra.get("recalled_outcome_if_known"),
                    "grader_verdict":     ra.get("grader_verdict"),
                })
    return records


def build_recall_df(records: list) -> pd.DataFrame:
    """
    One row per (model, market) with recall_score.
    Keeps only graded rows (recall_score is not None).
    market_id = condition_id.
    """
    rows = [
        {
            "market_id":     r["condition_id"],
            "domain":        r["domain"],
            "question_text": r.get("question_text", ""),
            "model":         r["model"],
            "recall_score":  r["recall_score"] if r["recall_score"] is not None else 0.0,
        }
        for r in records
        if any(rr["recall_score"] is not None
               for rr in records
               if rr["model"] == r["model"] and rr["domain"] == r["domain"])
    ]
    return pd.DataFrame(rows)


def load_forecast_records() -> list:
    """
    Load forecast JSON files (domain/forecast/*.json).
    These are open/future markets: no actual_resolution, but have market_price.
    Brier proxy = (p_yes - market_price)^2.
    Returns one dict per market-model pair.
    """
    records = []
    for domain in DOMAINS:
        fc_dir = RESEARCH_DIR / domain / "forecast"
        for path in sorted(fc_dir.glob("*.json")):
            model = path.stem.replace("_fc", "")
            try:
                items = json.loads(path.read_text())
            except Exception as e:
                print(f"[WARN] {path}: {e}")
                continue
            for item in items:
                fc = item.get("forecast") or {}
                probs = fc.get("probabilities") or {}
                mp = item.get("market_price") or {}
                p_yes = probs.get("Yes")
                market_price = mp.get("Yes")
                if p_yes is None or market_price is None:
                    continue
                records.append({
                    "model":         model,
                    "domain":        domain,
                    "condition_id":  item.get("condition_id", ""),
                    "question_text": item.get("title", ""),
                    "forecast_prob": float(p_yes),
                    "market_price":  float(market_price),
                    "brier_score":   (float(p_yes) - float(market_price)) ** 2,
                    "source":        "forecast",
                })
    return records


def build_forecast_df(recall_records: list, fc_records: list | None = None) -> pd.DataFrame:
    """
    One row per (model, market) with brier_score + forecast_prob.

    Sources:
      recall_records  — from load_recall_records(); Brier = (p_yes - outcome)^2
      fc_records      — from load_forecast_records(); Brier = (p_yes - market_price)^2

    Deduplicated by (model, condition_id): recall-sourced rows take priority.
    """
    rows = []

    # Recall-file rows (actual outcomes known)
    for r in recall_records:
        p = r["p_yes"]
        actual = r["actual_resolution"]
        if p is None or actual not in ("Yes", "No"):
            continue
        outcome = 1.0 if actual == "Yes" else 0.0
        rows.append({
            "market_id":     r["condition_id"],
            "domain":        r["domain"],
            "question_text": r.get("question_text", ""),
            "model":         r["model"],
            "forecast_prob": float(p),
            "outcome":       outcome,
            "market_price":  float("nan"),
            "brier_score":   (float(p) - outcome) ** 2,
            "source":        "recall",
        })

    seen = {(r["model"], r["market_id"]) for r in rows}

    # Forecast-file rows (Brier against market consensus price)
    if fc_records:
        for r in fc_records:
            key = (r["model"], r["condition_id"])
            if key in seen:
                continue
            rows.append({
                "market_id":     r["condition_id"],
                "domain":        r["domain"],
                "question_text": r["question_text"],
                "model":         r["model"],
                "forecast_prob": r["forecast_prob"],
                "outcome":       float("nan"),
                "market_price":  r["market_price"],
                "brier_score":   r["brier_score"],
                "source":        "forecast",
            })
            seen.add(key)

    return pd.DataFrame(rows)


def binary_entropy(p: float) -> float:
    p = max(min(float(p), 1 - 1e-10), 1e-10)
    return -p * math.log(p) - (1 - p) * math.log(1 - p)


def compute_domain_difficulty() -> dict:
    """Mean binary entropy of open-market prices per domain."""
    difficulty = {}
    for domain in DOMAINS:
        fc_dir = RESEARCH_DIR / domain / "forecast"
        seen = {}
        for path in sorted(fc_dir.glob("*.json")):
            try:
                items = json.loads(path.read_text())
            except Exception:
                continue
            for item in items:
                cid = item.get("condition_id", "")
                mp = item.get("market_price") or {}
                p = mp.get("Yes")
                if p is not None and cid not in seen:
                    seen[cid] = float(p)
        if seen:
            prices = list(seen.values())
            difficulty[domain] = {
                "mean_entropy": np.mean([binary_entropy(p) for p in prices]),
                "naive_brier":  np.mean([(p - 0.5) ** 2 for p in prices]),
                "n_markets":    len(prices),
            }
    return difficulty


def build_fidelity_matrix(records: list) -> list:
    """
    Returns one row per (model, domain) with:
      R_md          — mean recall_score (null → 0.0 for graded models)
      R_md_excl_null — mean recall_score for items that had a non-null score
      mean_brier    — mean Brier score for resolved items
    """
    buckets = defaultdict(list)
    for r in records:
        buckets[(r["model"], r["domain"])].append(r)

    rows = []
    for (model, domain), items in sorted(buckets.items()):
        any_graded = any(r["recall_score"] is not None for r in items)

        if any_graded:
            fidelity_scores = [
                r["recall_score"] if r["recall_score"] is not None else 0.0
                for r in items
            ]
            R_md = float(np.mean(fidelity_scores))
        else:
            fidelity_scores = []
            R_md = np.nan

        fidelity_graded = [r["recall_score"] for r in items if r["recall_score"] is not None]

        brier_scores = []
        for r in items:
            p = r["p_yes"]
            actual = r["actual_resolution"]
            if p is not None and actual in ("Yes", "No"):
                outcome = 1.0 if actual == "Yes" else 0.0
                brier_scores.append((p - outcome) ** 2)

        confident_wrong = [
            r for r in items
            if r["recall_score"] == 0.0 and r["recalled_outcome"] is not None
        ]

        rows.append({
            "model":             model,
            "model_display":     _display(model),
            "domain":            domain,
            "domain_short":      SHORT_DOMAIN[domain],
            "graded":            any_graded,
            "n_items":           len(items),
            "R_md":              R_md,
            "R_md_excl_null":    float(np.mean(fidelity_graded)) if fidelity_graded else np.nan,
            "n_graded":          len(fidelity_graded),
            "n_null":            sum(1 for r in items if r["recall_score"] is None),
            "n_correct":         sum(1 for r in items if r["recall_score"] == 1.0),
            "n_partial":         sum(1 for r in items if r["recall_score"] == 0.5),
            "n_wrong_explicit":  sum(1 for r in items if r["recall_score"] == 0.0),
            "n_confident_wrong": len(confident_wrong),
            "mean_brier":        np.mean(brier_scores) if brier_scores else np.nan,
            "n_brier":           len(brier_scores),
        })
    return rows


# ── Section 1: Recall aggregations ───────────────────────────────────────────

def modelwise_recall_all(panel_rows: list) -> pd.DataFrame:
    """
    Weighted-mean R_md across all domains for each model.
    Only graded (model, domain) cells contribute.
    """
    df = pd.DataFrame(panel_rows)
    df = df[df["graded"]]
    agg = (
        df.groupby("model")
        .apply(lambda g: pd.Series({
            "recall_mean":        np.average(g["R_md"],           weights=g["n_items"]),
            "recall_excl_null":   np.average(g["R_md_excl_null"].fillna(0), weights=g["n_items"]),
            "n_correct":          g["n_correct"].sum(),
            "n_partial":          g["n_partial"].sum(),
            "n_wrong":            g["n_wrong_explicit"].sum(),
            "n_null":             g["n_null"].sum(),
            "n_graded":           g["n_graded"].sum(),
            "n_total":            g["n_items"].sum(),
        }), include_groups=False)
        .reset_index()
    )
    agg["model_display"] = agg["model"].map(_display)
    agg = agg.sort_values("recall_mean", ascending=False)
    return agg


def modelwise_recall_by_domain(panel_rows: list) -> pd.DataFrame:
    """
    Pivot table: rows = models, columns = domains, values = R_md.
    NaN where model was not graded for a domain.
    """
    df = pd.DataFrame(panel_rows)
    df = df[df["graded"]]
    pivot = df.pivot(index="model", columns="domain_short", values="R_md")
    pivot.index = pivot.index.map(_display)
    pivot.index.name = "model"
    # Reorder columns by canonical domain order
    ordered_cols = [SHORT_DOMAIN[d] for d in DOMAINS if SHORT_DOMAIN[d] in pivot.columns]
    return pivot[ordered_cols]


# ── Section 2: Forecast Brier aggregations ───────────────────────────────────

def modelwise_brier_all(panel_rows: list) -> pd.DataFrame:
    """
    Weighted-mean Brier score across all domains for each model.
    """
    df = pd.DataFrame(panel_rows)
    df = df[df["n_brier"] >= 1]
    agg = (
        df.groupby("model")
        .apply(lambda g: pd.Series({
            "brier_mean": np.average(g["mean_brier"], weights=g["n_brier"]),
            "n_markets":  g["n_brier"].sum(),
        }), include_groups=False)
        .reset_index()
    )
    agg["model_display"] = agg["model"].map(_display)
    agg = agg.sort_values("brier_mean")
    return agg


def modelwise_brier_by_domain(panel_rows: list) -> pd.DataFrame:
    """
    Pivot table: rows = models, columns = domains, values = mean Brier score.
    """
    df = pd.DataFrame(panel_rows)
    df = df[df["n_brier"] >= 1]
    pivot = df.pivot(index="model", columns="domain_short", values="mean_brier")
    pivot.index = pivot.index.map(_display)
    pivot.index.name = "model"
    ordered_cols = [SHORT_DOMAIN[d] for d in DOMAINS if SHORT_DOMAIN[d] in pivot.columns]
    return pivot[ordered_cols]


# ── Section 3: Regression ─────────────────────────────────────────────────────

def build_regression_df(panel_rows: list, difficulty: dict) -> pd.DataFrame:
    """Merge panel rows with domain difficulty; filter to graded cells with >= 5 resolved markets."""
    rows = []
    for r in panel_rows:
        if not r["graded"] or r["n_brier"] < 5:
            continue
        diff = difficulty.get(r["domain"], {})
        if not diff:
            continue
        rows.append({
            "model":           r["model"],
            "model_display":   _display(r["model"]),
            "domain":          r["domain"],
            "domain_short":    SHORT_DOMAIN[r["domain"]],
            "brier":           r["mean_brier"],
            "R_md":            r["R_md"],
            "R_md_excl_null":  r["R_md_excl_null"],
            "difficulty":      diff["mean_entropy"],
            "naive_brier":     diff["naive_brier"],
        })
    df = pd.DataFrame(rows).dropna(subset=["brier", "R_md", "difficulty"])
    return df


def run_regression(panel_rows: list, difficulty: dict):
    """
    Fits four OLS specifications.

    Returns (results_dict, regression_df).
      results_dict keys: m1_simple, m2_difficulty, m3_model_fe, m4_excl_null_fe
    """
    df = build_regression_df(panel_rows, difficulty)

    results = {}
    results["m1_simple"]      = smf.ols("brier ~ R_md", data=df).fit()
    results["m2_difficulty"]  = smf.ols("brier ~ R_md + difficulty", data=df).fit()
    results["m3_model_fe"]    = smf.ols("brier ~ R_md + difficulty + C(model)", data=df).fit()

    df_excl = df.dropna(subset=["R_md_excl_null"])
    if len(df_excl) > df["model"].nunique() + 3:
        results["m4_excl_null_fe"] = smf.ols(
            "brier ~ R_md_excl_null + difficulty + C(model)", data=df_excl
        ).fit()

    return results, df


def regression_summary_df(results: dict) -> pd.DataFrame:
    """
    Compact summary table: one row per model × parameter with coef/SE/p.
    Useful for display in the notebook.
    """
    LABELS = {
        "m1_simple":       "M1: bivariate",
        "m2_difficulty":   "M2: + difficulty",
        "m3_model_fe":     "M3: + model FE  [headline]",
        "m4_excl_null_fe": "M4: excl-null + FE",
    }
    rows = []
    for key, label in LABELS.items():
        if key not in results:
            continue
        res = results[key]
        for param in res.params.index:
            pval = res.pvalues[param]
            stars = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
            rows.append({
                "model":   label,
                "param":   param,
                "coef":    round(res.params[param], 4),
                "SE":      round(res.bse[param], 4),
                "p":       round(pval, 4),
                "sig":     stars,
                "N":       int(res.nobs),
                "R2":      round(res.rsquared, 3),
                "adj_R2":  round(res.rsquared_adj, 3),
            })
    return pd.DataFrame(rows)


# ── Plot helpers ──────────────────────────────────────────────────────────────

def _model_colors(model_display_series: pd.Series) -> list:
    return [PALETTE.get(m, "#999999") for m in model_display_series]


def plot_recall_bar(agg_df: pd.DataFrame, ax=None, title: str = "Modelwise Recall Score (all markets)"):
    """Horizontal bar chart: mean R_md per model."""
    plt = _plt()
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4))
    colors = _model_colors(agg_df["model_display"])
    bars = ax.barh(agg_df["model_display"], agg_df["recall_mean"], color=colors, edgecolor="white", height=0.6)
    ax.set_xlabel("Mean Recall Score  R̄_{m}  (null → 0.0)")
    ax.set_xlim(0, 1.05)
    ax.set_title(title)
    for bar, v in zip(bars, agg_df["recall_mean"]):
        ax.text(v + 0.01, bar.get_y() + bar.get_height() / 2,
                f"{v:.3f}", va="center", fontsize=9)
    ax.invert_yaxis()
    return ax


def plot_brier_bar(agg_df: pd.DataFrame, ax=None, title: str = "Modelwise Brier Score (all markets)"):
    """Horizontal bar chart: mean Brier per model (lower = better)."""
    plt = _plt()
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4))
    colors = _model_colors(agg_df["model_display"])
    bars = ax.barh(agg_df["model_display"], agg_df["brier_mean"], color=colors, edgecolor="white", height=0.6)
    ax.set_xlabel("Mean Brier Score  (lower = better)")
    ax.set_title(title)
    for bar, v in zip(bars, agg_df["brier_mean"]):
        ax.text(v + 0.001, bar.get_y() + bar.get_height() / 2,
                f"{v:.4f}", va="center", fontsize=9)
    ax.invert_yaxis()
    return ax


def plot_recall_heatmap(pivot: pd.DataFrame, ax=None, title: str = "Recall Score R_{m,d} by Model × Domain"):
    """Annotated heatmap of recall scores."""
    plt = _plt(); sns = _sns()
    if ax is None:
        _, ax = plt.subplots(figsize=(13, 4))
    sns.heatmap(
        pivot, ax=ax, cmap="YlGn", vmin=0, vmax=1,
        annot=True, fmt=".2f", linewidths=0.4,
        cbar_kws={"label": "R_md"},
    )
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=35)
    ax.tick_params(axis="y", rotation=0)
    return ax


def plot_brier_heatmap(pivot: pd.DataFrame, ax=None, title: str = "Brier Score by Model × Domain"):
    """Annotated heatmap of Brier scores (lower = better → reversed colormap)."""
    plt = _plt(); sns = _sns()
    if ax is None:
        _, ax = plt.subplots(figsize=(13, 4))
    sns.heatmap(
        pivot, ax=ax, cmap="YlOrRd_r", vmin=0,
        annot=True, fmt=".3f", linewidths=0.4,
        cbar_kws={"label": "Brier"},
    )
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=35)
    ax.tick_params(axis="y", rotation=0)
    return ax


def plot_regression_scatter(reg_df: pd.DataFrame, ax=None,
                             title: str = "Recall Fidelity vs Forecast Brier  (per model × domain)"):
    """Scatter: R_md on x-axis, Brier on y-axis, color by model, OLS line."""
    plt = _plt()
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 6))
    for model, grp in reg_df.groupby("model_display"):
        color = PALETTE.get(model, "#999999")
        ax.scatter(grp["R_md"], grp["brier"], label=model, color=color, alpha=0.75, s=60, edgecolors="white", linewidths=0.5)

    # OLS line
    if len(reg_df) >= 3:
        x = reg_df["R_md"].values
        y = reg_df["brier"].values
        mask = ~np.isnan(x) & ~np.isnan(y)
        m, b = np.polyfit(x[mask], y[mask], 1)
        xline = np.linspace(x[mask].min(), x[mask].max(), 100)
        ax.plot(xline, m * xline + b, color="black", linewidth=1.5, linestyle="--", label=f"OLS  β={m:.3f}")

    ax.set_xlabel("Recall Fidelity  R_{m,d}  (null → 0.0)")
    ax.set_ylabel("Mean Brier Score")
    ax.set_title(title)
    ax.legend(fontsize=8, framealpha=0.7)
    return ax


def plot_regression_coef(results: dict, ax=None,
                          title: str = "β(R_md) across regression specifications"):
    """
    Coefficient plot: β on R_md with 95 % CI for each regression model.
    """
    plt = _plt()
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 3.5))

    LABELS = {
        "m1_simple":       "M1: bivariate",
        "m2_difficulty":   "M2: + difficulty",
        "m3_model_fe":     "M3: + model FE",
        "m4_excl_null_fe": "M4: excl-null FE",
    }
    recall_params = {"m1_simple": "R_md", "m2_difficulty": "R_md",
                     "m3_model_fe": "R_md", "m4_excl_null_fe": "R_md_excl_null"}

    y_ticks, y_labels, betas, lo95, hi95 = [], [], [], [], []
    for i, (key, label) in enumerate(LABELS.items()):
        if key not in results:
            continue
        res = results[key]
        param = recall_params[key]
        if param not in res.params:
            continue
        ci = res.conf_int().loc[param]
        y_ticks.append(i)
        y_labels.append(label)
        betas.append(res.params[param])
        lo95.append(ci[0])
        hi95.append(ci[1])

    for i, (beta, lo, hi, label) in enumerate(zip(betas, lo95, hi95, y_labels)):
        color = "#E53935" if beta > 0 else "#43A047"
        ax.errorbar(beta, i, xerr=[[beta - lo], [hi - beta]],
                    fmt="o", color=color, capsize=5, markersize=7, linewidth=2)

    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels)
    ax.set_xlabel("β coefficient on recall fidelity")
    ax.set_title(title)
    ax.invert_yaxis()
    return ax


def plot_recall_score_breakdown(agg_df: pd.DataFrame, ax=None,
                                 title: str = "Recall Score Breakdown by Model"):
    """
    Stacked bar: proportions of 1.0 / 0.5 / 0.0 / no-recall per model.
    """
    plt = _plt()
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 4))

    df = agg_df.copy()
    df["pct_correct"] = df["n_correct"] / df["n_graded"]
    df["pct_partial"]  = df["n_partial"]  / df["n_graded"]
    df["pct_wrong"]   = df["n_wrong"]   / df["n_graded"]
    df["pct_null"]    = df["n_null"]    / df["n_graded"]
    df = df.set_index("model_display")

    cats = [("pct_correct", "1.0 correct+clean",  "#43A047"),
            ("pct_partial",  "0.5 correct+errors", "#FDD835"),
            ("pct_wrong",   "0.0 wrong",           "#E53935"),
            ("pct_null",    "null no-recall",       "#BDBDBD")]

    bottoms = np.zeros(len(df))
    for col, label, color in cats:
        ax.bar(df.index, df[col], bottom=bottoms, label=label, color=color, edgecolor="white")
        bottoms += df[col].values

    ax.set_ylabel("Proportion of items")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.tick_params(axis="x", rotation=25)
    return ax
