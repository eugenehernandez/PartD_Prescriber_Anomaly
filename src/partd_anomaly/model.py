"""Isolation Forest and the statistical baseline it is compared against."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .config import Config


def isolation_forest_scores(z: pd.DataFrame, cfg: Config, seed: int | None = None) -> tuple[pd.Series, IsolationForest]:
    """Fit on the peer-relative z matrix. Higher score = more anomalous.

    contamination is left at 'auto' on purpose. It only moves sklearn's internal
    threshold and does not change the ranking. The share flagged for review is set
    separately by cfg.flag_share, so both methods are cut at the same point.
    """
    model = IsolationForest(
        n_estimators=cfg.n_estimators,
        max_samples=min(cfg.max_samples, len(z)),
        max_features=cfg.max_features,
        contamination="auto",
        random_state=cfg.seed if seed is None else seed,
        n_jobs=-1,
    )
    model.fit(z.to_numpy())
    return pd.Series(-model.score_samples(z.to_numpy()), index=z.index, name="if_score"), model


def peer_z_baseline_scores(z: pd.DataFrame) -> pd.Series:
    """The rule a program integrity analyst would write by hand: how far is this
    prescriber from peers on their single most extreme measure? The mean absolute
    z breaks ties among prescribers who hit the cap."""
    a = z.abs()
    return (a.max(axis=1) + 0.01 * a.mean(axis=1)).rename("z_score")


def top_k_mask(score: pd.Series, share: float) -> pd.Series:
    k = max(1, int(round(share * len(score))))
    cutoff_idx = score.sort_values(ascending=False, kind="mergesort").index[:k]
    return score.index.isin(cutoff_idx)
