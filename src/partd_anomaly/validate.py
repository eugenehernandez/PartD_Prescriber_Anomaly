"""Checks that do not require fraud labels, plus the later-exclusion check.

There are no ground-truth fraud labels in public data. Later exclusion from
Medicare by the HHS Office of Inspector General is an imperfect but real outcome:
if flagged prescribers are excluded more often than the base rate, the scores carry
signal. Most flagged prescribers will never be excluded, and that is expected.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from scipy.stats import hypergeom, spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

from .config import Config
from .model import isolation_forest_scores, top_k_mask


def label_metrics(score: pd.Series, label: pd.Series, share: float) -> dict:
    n, n_pos = len(label), int(label.sum())
    flagged = top_k_mask(score, share)
    k, hits = int(flagged.sum()), int(label[flagged].sum())
    base = n_pos / n if n else np.nan
    out = {
        "n_prescribers": n,
        "n_excluded_later": n_pos,
        "base_rate_pct": 100 * base,
        "n_flagged": k,
        "excluded_among_flagged": hits,
        "precision_at_k_pct": 100 * hits / k if k else np.nan,
        "lift_at_k": (hits / k) / base if k and base else np.nan,
        # Chance of seeing this many or more by luck if flags were random.
        "p_value_vs_random": float(hypergeom.sf(hits - 1, n, n_pos, k)) if n_pos else np.nan,
        "auroc": np.nan,
        "average_precision": np.nan,
    }
    if 0 < n_pos < n:
        out["auroc"] = roc_auc_score(label, score)
        out["average_precision"] = average_precision_score(label, score)
    return out


def lift_curve(scores: dict, label: pd.Series, shares=(0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.10)) -> pd.DataFrame:
    rows = []
    for method, s in scores.items():
        for sh in shares:
            m = label_metrics(s, label, sh)
            rows.append({"method": method, "flag_share_pct": 100 * sh,
                         "n_flagged": m["n_flagged"], "excluded_among_flagged": m["excluded_among_flagged"],
                         "lift": m["lift_at_k"]})
    return pd.DataFrame(rows)


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    inter, union = np.logical_and(a, b).sum(), np.logical_or(a, b).sum()
    return inter / union if union else np.nan


def agreement(score_a: pd.Series, score_b: pd.Series, share: float) -> dict:
    fa, fb = top_k_mask(score_a, share), top_k_mask(score_b, share)
    return {
        "flag_share_pct": 100 * share,
        "flagged_by_both": int(np.logical_and(fa, fb).sum()),
        "flagged_by_isolation_forest_only": int(np.logical_and(fa, ~fb).sum()),
        "flagged_by_baseline_only": int(np.logical_and(~fa, fb).sum()),
        "jaccard": jaccard(fa, fb),
        "spearman_rank_correlation": float(spearmanr(score_a, score_b).statistic),
    }


def stability(z: pd.DataFrame, cfg: Config) -> float:
    """Mean pairwise Jaccard of the flagged set across random seeds. Near 1 means the
    flags do not depend on the luck of the trees."""
    masks = [top_k_mask(isolation_forest_scores(z, cfg, seed=s)[0], cfg.flag_share) for s in cfg.stability_seeds]
    return float(np.mean([jaccard(a, b) for a, b in itertools.combinations(masks, 2)]))
