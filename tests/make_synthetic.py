"""Make small synthetic stand-ins for the Part D and LEIE files.

They use the real column names and suppression conventions, so the full pipeline
can be tested end to end without downloading anything. About 1% of prescribers get
a planted anomaly, and later exclusions are made more common among them, so a
working pipeline should show lift well above 1. Numbers here mean nothing clinically.

    python tests/make_synthetic.py --out tests/synthetic
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SPECIALTIES = {
    # name: (median cost per beneficiary, claims per beneficiary, opioid share, brand share, weight)
    "Family Practice": (900, 9, 0.05, 0.12, 0.22),
    "Internal Medicine": (1100, 10, 0.04, 0.14, 0.22),
    "Nurse Practitioner": (800, 7, 0.05, 0.11, 0.18),
    "Physician Assistant": (700, 6, 0.06, 0.10, 0.08),
    "Cardiology": (1600, 8, 0.01, 0.25, 0.06),
    "Psychiatry": (1300, 8, 0.01, 0.15, 0.05),
    "Hematology-Oncology": (9000, 5, 0.08, 0.45, 0.03),
    "Pain Management": (1200, 9, 0.45, 0.10, 0.02),
    "Dermatology": (700, 3, 0.002, 0.30, 0.03),
    "Dentist": (60, 1.3, 0.25, 0.02, 0.10),
    "Podiatry": (150, 2, 0.08, 0.05, 0.01),
}
STATES = ["FL", "TX", "CA", "NY", "PA", "OH", "GA", "AL", "MS", "VT"]
STATE_W = [0.14, 0.13, 0.16, 0.12, 0.09, 0.08, 0.08, 0.08, 0.07, 0.05]


def blank_small(x):
    """CMS suppression: counts from 1 to 10 are published as blank."""
    x = np.round(x).astype("float")
    return np.where((x > 0) & (x < 11), np.nan, x)


def make(n: int, data_year: int, seed: int):
    rng = np.random.default_rng(seed)
    names = list(SPECIALTIES)
    w = np.array([SPECIALTIES[s][4] for s in names])
    spec = rng.choice(names, n, p=w / w.sum())
    p = np.array([SPECIALTIES[s] for s in spec])
    cost_b, clm_b, opi, brn = p[:, 0].astype(float), p[:, 1].astype(float), p[:, 2].astype(float), p[:, 3].astype(float)

    benes = np.round(np.exp(rng.normal(np.log(120), 0.9, n))) + 1
    clms_per_bene = clm_b * np.exp(rng.normal(0, 0.25, n))
    cost_per_bene = cost_b * np.exp(rng.normal(0, 0.35, n))
    days_per_clm = 30 * np.exp(rng.normal(0.4, 0.2, n))
    opioid_share = np.clip(opi * np.exp(rng.normal(0, 0.5, n)), 0, 0.95)
    brand_share = np.clip(brn * np.exp(rng.normal(0, 0.35, n)), 0, 0.95)
    risk = np.exp(rng.normal(np.log(1.2), 0.25, n))

    # Planted anomalies: a pill-mill pattern, a high-cost brand pattern, and extreme volume.
    anomaly = rng.random(n) < 0.01
    kind = rng.integers(0, 3, n)
    pill = anomaly & (kind == 0)
    cost = anomaly & (kind == 1)
    volm = anomaly & (kind == 2)
    opioid_share[pill] = np.clip(opioid_share[pill] * 6 + 0.3, 0, 0.95)
    clms_per_bene[pill] *= 2.2
    cost_per_bene[cost] *= 5
    brand_share[cost] = np.clip(brand_share[cost] * 3, 0, 0.95)
    benes[volm] *= 8
    clms_per_bene[volm] *= 1.8

    tot_clms = np.round(benes * clms_per_bene) + 11
    tot_day = np.round(tot_clms * days_per_clm)
    tot_cost = np.round(benes * cost_per_bene, 2)

    npi = np.unique(rng.integers(1_000_000_000, 2_000_000_000, n * 2))
    npi = rng.permutation(npi)[:n]
    ent = np.where(rng.random(n) < 0.03, "O", "I")
    cntry = np.where(rng.random(n) < 0.002, "CA", "US")
    state = rng.choice(STATES, n, p=STATE_W)

    partd = pd.DataFrame({
        "Prscrbr_NPI": npi,
        "Prscrbr_Last_Org_Name": "SYNTHETIC",
        "Prscrbr_First_Name": "TEST",
        "Prscrbr_Ent_Cd": ent,
        "Prscrbr_City": "ANYTOWN",
        "Prscrbr_State_Abrvtn": state,
        "Prscrbr_Cntry": cntry,
        "Prscrbr_Type": spec,
        "Prscrbr_Type_Src": "S",
        "Tot_Clms": tot_clms,
        "Tot_30day_Fills": np.round(tot_day / 30, 1),
        "Tot_Drug_Cst": tot_cost,
        "Tot_Day_Suply": tot_day,
        "Tot_Benes": blank_small(benes),
        "Brnd_Tot_Clms": blank_small(tot_clms * brand_share),
        "Gnrc_Tot_Clms": blank_small(tot_clms * (1 - brand_share)),
        "Opioid_Tot_Clms": blank_small(tot_clms * opioid_share),
        "Opioid_LA_Tot_Clms": blank_small(tot_clms * opioid_share * 0.15),
        "Antbtc_Tot_Clms": blank_small(tot_clms * 0.04 * np.exp(rng.normal(0, 0.4, n))),
        "Bene_Avg_Risk_Scre": np.round(risk, 4),
    })
    # A few rows with no specialty, as in the real file.
    partd.loc[rng.random(n) < 0.001, "Prscrbr_Type"] = ""

    # LEIE. Later exclusion is far more likely for planted anomalies.
    p_excl = np.where(anomaly, 0.08, 0.0015)
    later = rng.random(n) < p_excl
    earlier = (~later) & (rng.random(n) < 0.0005)
    def dates(k, y0, y1):
        y = rng.integers(y0, y1 + 1, k)
        return [int(f"{yy}{rng.integers(1, 13):02d}{rng.integers(1, 29):02d}") for yy in y]
    types = rng.choice(["1128a1", "1128a3", "1128b4", "1128b7", "1128a2"], later.sum(), p=[0.3, 0.2, 0.35, 0.1, 0.05])
    leie = pd.DataFrame({
        "LASTNAME": "SYNTHETIC", "FIRSTNAME": "TEST", "MIDNAME": "", "BUSNAME": "", "GENERAL": "",
        "SPECIALTY": "", "UPIN": "",
        "NPI": [f"{x:010d}" for x in npi[later]] + [f"{x:010d}" for x in npi[earlier]],
        "DOB": "", "ADDRESS": "", "CITY": "", "STATE": "", "ZIP": "",
        "EXCLTYPE": list(types) + ["1128b4"] * int(earlier.sum()),
        "EXCLDATE": dates(later.sum(), data_year + 1, data_year + 2) + dates(earlier.sum(), data_year - 4, data_year),
        "REINDATE": "00000000", "WAIVERDATE": "00000000", "WVRSTATE": "",
    })
    # Exclusions without an NPI, which the pipeline must drop.
    extra = pd.DataFrame({c: leie[c].iloc[:1].repeat(300).values for c in leie.columns})
    extra["NPI"] = "0000000000"
    leie = pd.concat([leie, extra], ignore_index=True)
    return partd, leie


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tests/synthetic")
    ap.add_argument("--n", type=int, default=60000)
    ap.add_argument("--year", type=int, default=2023)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    partd, leie = make(a.n, a.year, a.seed)
    partd.to_csv(out / "partd_synthetic.csv", index=False)
    leie.to_csv(out / "leie_synthetic.csv", index=False)
    print(f"wrote {len(partd):,} prescribers and {len(leie):,} exclusions to {out}")
