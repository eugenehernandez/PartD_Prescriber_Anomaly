"""Project settings. Every analytic choice lives here so it can be logged to MLflow
and varied in the sensitivity sweep. Reasons for each default are in
docs/modeling_decisions.md."""

from dataclasses import asdict, dataclass, field


@dataclass
class Config:
    # Data year of the Part D file. Exclusions must be dated after its last day.
    data_year: int = 2023

    # Step 5. Minimum national prescriber count for a specialty to be analyzed.
    min_specialty_n: int = 100

    # Peer groups. Specialty within state when the group is large enough,
    # otherwise specialty nationally.
    peer_mode: str = "specialty_state"      # or "specialty_national"
    min_peer_n: int = 50

    # Features fed to both methods (all peer-relative robust z-scores).
    features: list = field(default_factory=lambda: [
        "cost_per_bene", "clms_per_bene", "cost_per_day", "days_per_clm",
        "brand_share", "opioid_share", "la_opioid_share", "antibiotic_share",
        "log_benes", "bene_risk_score",
    ])
    # Skewed features are logged before scoring.
    log_features: list = field(default_factory=lambda: [
        "cost_per_bene", "clms_per_bene", "cost_per_day", "days_per_clm",
    ])
    # How each feature is compared with peers. "robust" uses the median and MAD.
    # "rank" converts each value to its percentile within the peer group, then to
    # a normal score, so every peer group has the same tail shape by construction.
    # Declared as the primary method for 2023 before that run (see D21).
    # The 2024 primary analysis used "robust".
    scaling: str = "rank"
    # z-scores are capped so a single extreme value cannot dominate.
    z_cap: float = 10.0
    # If True, only above-peer deviations count (z below 0 set to 0).
    one_sided: bool = False

    # Isolation Forest
    n_estimators: int = 300
    max_samples: int = 256
    max_features: float = 1.0
    seed: int = 20261111

    # Share of prescribers flagged for review.
    flag_share: float = 0.01

    # Seeds used to measure how stable the flagged set is.
    stability_seeds: tuple = (1, 2, 3, 4, 5)

    @property
    def data_year_end(self) -> int:
        return int(f"{self.data_year}1231")

    def as_params(self) -> dict:
        d = asdict(self)
        d["features"] = ",".join(self.features)
        d["log_features"] = ",".join(self.log_features)
        d["stability_seeds"] = ",".join(map(str, self.stability_seeds))
        return d
