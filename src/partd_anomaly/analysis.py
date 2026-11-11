"""Model, baseline, validation, and the sensitivity sweep. Shared by run_all.py
and the Databricks notebook so both produce identical outputs."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .features import build_feature_matrix, top_reasons
from .model import isolation_forest_scores, peer_z_baseline_scores, top_k_mask
from .tracking import Tracker
from .validate import agreement, label_metrics, lift_curve, stability

SMALL_CELL = 11  # same rule CMS uses: counts from 1 to 10 are not published


def suppress(n: int) -> str:
    return "<11" if 0 < n < SMALL_CELL else f"{n}"


def score_once(df: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    df, z = build_feature_matrix(df, cfg)
    if_score, _ = isolation_forest_scores(z, cfg)
    z_score = peer_z_baseline_scores(z)
    return df, z, if_score, z_score


def max_specialty_flag_rate(flagged: np.ndarray, specialty: pd.Series, min_n: int = 5000) -> float:
    """Highest flag rate among large specialties. Peer comparison removes average
    differences between specialties, so a large value means one specialty's tails
    are much heavier than the others'."""
    t = pd.DataFrame({"f": flagged, "s": specialty.to_numpy()}).groupby("s")["f"].agg(["mean", "size"])
    return float(100 * t.loc[t["size"] >= min_n, "mean"].max())


def sweep_variants(base: Config) -> list[tuple[str, Config]]:
    """Each variant changes one choice from the pre-specified primary analysis."""
    r = dataclasses.replace
    return [
        ("primary", base),
        ("peer group national only", r(base, peer_mode="specialty_national")),
        ("larger state peer minimum (100)", r(base, min_peer_n=100)),
        ("above-peer deviations only", r(base, one_sided=True)),
        ("without patient risk score", r(base, features=[f for f in base.features if f != "bene_risk_score"])),
        ("max_samples 1024", r(base, max_samples=1024)),
        ("n_estimators 100", r(base, n_estimators=100)),
        ("max_features 0.5", r(base, max_features=0.5)),
        ("robust (median and MAD) peer scores" if base.scaling == "rank" else "rank-based peer scores",
         r(base, scaling="robust" if base.scaling == "rank" else "rank")),
    ]


def run_analysis(labeled: pd.DataFrame, cfg: Config, out_dir: Path, tracker: Tracker | None = None,
                 run_sweep: bool = True) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    (out_dir / "private").mkdir(parents=True, exist_ok=True)
    tracker = tracker or Tracker(enabled=False)
    # SQL engines return rows in no fixed order. Sorting makes the forest reproducible.
    labeled = labeled.sort_values("npi", kind="mergesort").reset_index(drop=True)
    label = labeled["excluded_later"].astype(int)
    label_fraud = labeled["excluded_later_fraud"].astype(int)

    # ---- Primary analysis (pre-specified, chosen before looking at the labels) ----
    with tracker.run("primary"):
        tracker.params(cfg.as_params())
        df, z, if_score, z_score = score_once(labeled, cfg)
        scores = {"isolation_forest": if_score, "peer_z_baseline": z_score}

        rng = np.random.default_rng(cfg.seed)
        random_score = pd.Series(rng.random(len(df)), index=df.index)

        val_rows = []
        for outcome, lab in (("any exclusion", label), ("fraud-related exclusion", label_fraud)):
            for method, s in {**scores, "random (reference)": random_score}.items():
                val_rows.append({"outcome": outcome, "method": method, **label_metrics(s, lab, cfg.flag_share)})
        validation = pd.DataFrame(val_rows)

        agree = pd.DataFrame([agreement(if_score, z_score, sh) for sh in (0.005, 0.01, 0.05)])
        stab = stability(z, cfg)
        curve = lift_curve(scores, label)

        primary = validation[(validation.outcome == "any exclusion") & (validation.method == "isolation_forest")].iloc[0]
        tracker.metrics(primary.drop(["outcome", "method"]).to_dict(), prefix="if_")
        base_row = validation[(validation.outcome == "any exclusion") & (validation.method == "peer_z_baseline")].iloc[0]
        tracker.metrics(base_row.drop(["outcome", "method"]).to_dict(), prefix="baseline_")
        tracker.metrics({"stability_jaccard": stab, "jaccard_if_vs_baseline": agree.loc[1, "jaccard"]})

        # ---- Flag table (private, contains NPIs) and aggregate summaries (public) ----
        flagged_if = top_k_mask(if_score, cfg.flag_share)
        flagged_z = top_k_mask(z_score, cfg.flag_share)
        reasons = top_reasons(z)
        private = df.assign(if_score=if_score, z_score=z_score, flagged_if=flagged_if,
                            flagged_baseline=flagged_z, top_reasons=reasons)
        private = private[private.flagged_if | private.flagged_baseline].sort_values("if_score", ascending=False)
        private_cols = ["npi", "specialty", "state", "peer_group", "tot_benes", "tot_clms", "tot_drug_cst",
                        "if_score", "z_score", "flagged_if", "flagged_baseline", "top_reasons",
                        "excluded_later", "excl_type", "excl_date"]
        private[private_cols].to_csv(out_dir / "private" / "flagged_prescribers.csv", index=False)

        by_spec = (
            df.assign(flagged=flagged_if)
            .groupby("specialty")
            .agg(prescribers=("npi", "size"), flagged=("flagged", "sum"))
            .reset_index()
        )
        by_spec["flag_rate_pct"] = (100 * by_spec.flagged / by_spec.prescribers).round(2)
        by_spec = by_spec.sort_values("flagged", ascending=False)
        by_spec["flagged"] = by_spec["flagged"].astype(int).map(suppress)
        by_spec.loc[by_spec.flagged == "<11", "flag_rate_pct"] = np.nan

        lead = z.abs().idxmax(axis=1)[flagged_if].value_counts().rename_axis("leading_feature").reset_index(name="flagged")
        lead["flagged"] = lead["flagged"].astype(int).map(suppress)

        validation.round(4).to_csv(out_dir / "validation.csv", index=False)
        agree.round(4).to_csv(out_dir / "agreement.csv", index=False)
        curve.round(4).to_csv(out_dir / "lift_curve.csv", index=False)
        by_spec.to_csv(out_dir / "flags_by_specialty.csv", index=False)
        lead.to_csv(out_dir / "flags_by_leading_feature.csv", index=False)
        pd.DataFrame([{"metric": "mean pairwise Jaccard of flagged set across seeds",
                       "seeds": cfg.as_params()["stability_seeds"], "value": round(stab, 4)}]
                     ).to_csv(out_dir / "stability.csv", index=False)
        fig = plot_lift(curve, out_dir / "figures" / "lift_by_method.png")
        for f in ["validation.csv", "agreement.csv", "lift_curve.csv", "flags_by_specialty.csv",
                  "flags_by_leading_feature.csv", "stability.csv"]:
            tracker.artifact(str(out_dir / f))
        if fig:
            tracker.artifact(str(fig))

    # ---- Sensitivity sweep. Reported, never used to pick the primary settings. ----
    sens = None
    if run_sweep:
        rows = []
        for name, vcfg in sweep_variants(cfg):
            with tracker.run(f"sensitivity: {name}"):
                tracker.params(vcfg.as_params())
                tracker.tags({"analysis": "sensitivity"})
                v_if = if_score if name == "primary" else score_once(labeled, vcfg)[2]
                m = label_metrics(v_if, label, vcfg.flag_share)
                overlap = float(np.logical_and(top_k_mask(v_if, cfg.flag_share), flagged_if).sum() / flagged_if.sum())
                tracker.metrics({**m, "overlap_with_primary": overlap})
                spread = max_specialty_flag_rate(top_k_mask(v_if, cfg.flag_share), labeled["specialty"])
                tracker.metrics({"max_specialty_flag_rate_pct": spread})
                rows.append({"variant": name, "lift_at_k": m["lift_at_k"], "auroc": m["auroc"],
                             "average_precision": m["average_precision"],
                             "excluded_among_flagged": m["excluded_among_flagged"],
                             "share_of_primary_flags_kept": overlap,
                             "max_specialty_flag_rate_pct": spread})
        sens = pd.DataFrame(rows).round(4)
        sens.to_csv(out_dir / "sensitivity.csv", index=False)

    return {"validation": validation, "agreement": agree, "stability": stab, "lift_curve": curve,
            "flags_by_specialty": by_spec, "sensitivity": sens}


def plot_lift(curve: pd.DataFrame, path: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    colors = {"isolation_forest": "#2a78d6", "peer_z_baseline": "#eb6834"}
    labels = {"isolation_forest": "Isolation Forest", "peer_z_baseline": "Peer z-score baseline"}
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for method, g in curve.groupby("method"):
        ax.plot(g.flag_share_pct, g.lift, marker="o", markersize=5, linewidth=2,
                color=colors.get(method), label=labels.get(method, method))
    ax.axhline(1, color="#9a9994", linewidth=1, linestyle="--")
    ax.text(curve.flag_share_pct.min(), 1, " random flags", va="bottom", fontsize=8, color="#52514e")
    ax.set_xscale("log")
    ax.minorticks_off()
    ax.set_xticks(sorted(curve.flag_share_pct.unique()))
    ax.set_xticklabels([f"{v:g}%" for v in sorted(curve.flag_share_pct.unique())])
    ax.set_xlabel("Share of prescribers flagged", color="#52514e")
    ax.set_ylabel("Lift in later OIG exclusion", color="#52514e")
    ax.set_title("How much more often flagged prescribers are later excluded", loc="left",
                 fontsize=11, color="#0b0b0b")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.8)
    ax.tick_params(colors="#52514e", labelsize=8)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
