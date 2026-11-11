"""Peer-relative features.

A cancer specialist and a family physician should not be judged on the same scale,
so every feature is expressed as a robust z-score within the prescriber's peer group:
    z = (x - peer median) / (1.4826 * peer MAD)
The median and MAD are used instead of the mean and standard deviation because
prescribing data is heavily skewed and the outliers we are looking for would
otherwise inflate the scale they are measured against.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config


def assign_peer_group(df: pd.DataFrame, cfg: Config) -> pd.Series:
    national = df["specialty"]
    if cfg.peer_mode == "specialty_national":
        return national + " | US"
    state_key = df["specialty"] + " | " + df["state"]
    size = state_key.map(state_key.value_counts())
    return np.where(size >= cfg.min_peer_n, state_key, national + " | US")


MIN_OBSERVED = 20   # published values a group needs before its own median and spread are used


def _peer_stats(x: pd.Series, groups: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Median, robust scale, and count of published values per group, aligned to rows.
    Missing values are ignored, so suppressed rows cannot drag the scale toward zero."""
    g = x.groupby(groups)
    med = g.transform("median")
    dev = (x - med).abs()
    mad = dev.groupby(groups).transform("median") * 1.4826
    # When most of a group sits at one value (for example, no opioid claims), the MAD
    # is 0. Use the mean absolute deviation instead, times sqrt(pi/2) = 1.2533, which
    # makes it estimate the standard deviation for normal data, as 1.4826 does for the MAD.
    meanad = dev.groupby(groups).transform("mean") * 1.253314
    scale = mad.where(mad > 1e-9, meanad)
    n_obs = g.transform("count")
    return med, scale, n_obs


def robust_z(x: pd.Series, groups: pd.Series, fallback_groups: pd.Series | None = None) -> pd.Series:
    """Peer-relative robust z-score. Statistics come from published values only.
    A group with fewer than MIN_OBSERVED published values borrows the fallback
    group's statistics. Suppressed values score 0, meaning no evidence either way."""
    med, scale, n_obs = _peer_stats(x, groups)
    if fallback_groups is not None:
        f_med, f_scale, _ = _peer_stats(x, fallback_groups)
        thin = n_obs < MIN_OBSERVED
        med, scale = med.where(~thin, f_med), scale.where(~thin, f_scale)
    z = (x - med) / scale.where(scale > 1e-9)
    return z.fillna(0.0)


def rank_normal_z(x: pd.Series, groups: pd.Series) -> pd.Series:
    """Percentile within the peer group (published values only), mapped to a normal
    score. Tied values share their average rank. Suppressed values score 0."""
    from scipy.stats import norm

    g = x.groupby(groups)
    pct = (g.rank(method="average") - 0.5) / g.transform("count")
    return pd.Series(norm.ppf(pct), index=x.index).fillna(0.0)


def build_feature_matrix(df: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (df with peer_group added, Z matrix of peer-relative scores)."""
    df = df.copy()
    df["peer_group"] = assign_peer_group(df, cfg)
    df["log_benes"] = np.log(df["tot_benes"])

    z = pd.DataFrame(index=df.index)
    for feat in cfg.features:
        x = df[feat].astype(float)
        if feat in cfg.log_features:
            x = np.log(x.where(x > 0))
        if cfg.scaling == "rank":
            z[feat] = rank_normal_z(x, df["peer_group"])
        else:
            z[feat] = robust_z(x, df["peer_group"], df["specialty"])

    z = z.clip(-cfg.z_cap, cfg.z_cap)
    if cfg.one_sided:
        z = z.clip(lower=0)
    return df, z


def top_reasons(z: pd.DataFrame, k: int = 3) -> pd.Series:
    """Plain-language reason codes: the k features furthest from the peer group."""
    names = np.array(z.columns)
    order = np.argsort(-z.abs().to_numpy(), axis=1)[:, :k]
    vals = z.to_numpy()
    out = []
    for i, idx in enumerate(order):
        parts = [f"{names[j]} {'high' if vals[i, j] > 0 else 'low'} (z={vals[i, j]:.1f})" for j in idx]
        out.append("; ".join(parts))
    return pd.Series(out, index=z.index)
