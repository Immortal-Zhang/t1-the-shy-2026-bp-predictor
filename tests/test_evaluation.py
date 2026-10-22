"""Metric and chronological-split unit tests, with artificial test fixtures."""

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import log_loss

from worlds_predictor.evaluation import metrics, paired_day_bootstrap, temporal_split


def split_fixture():
    records = []
    for month in range(1, 5):
        for number in range(4):
            date = pd.Timestamp(f"2024-{month:02d}-10T12:00:00Z") + pd.Timedelta(days=number)
            records.append({"game_id": f"test-only-{month}-{number}", "date": date,
                            "available_at": date + pd.Timedelta(hours=1), "blue_win": number % 2})
    config = {"train_end": "2024-02-01T00:00:00Z", "validation_end": "2024-03-01T00:00:00Z",
              "calibration_end": "2024-04-01T00:00:00Z", "as_of": "2024-05-01T00:00:00Z",
              "min_train": 2, "min_eval": 2}
    return pd.DataFrame(records), config


def test_metrics_match_hand_calculated_binary_scores():
    result = metrics([0, 1], [0.25, 0.75])
    assert result["accuracy"] == 1
    assert result["roc_auc"] == 1
    assert result["log_loss"] == pytest.approx(-np.log(.75))
    assert result["brier_score"] == pytest.approx(.25 ** 2)
    assert result["ece_10"] == pytest.approx(.25)
    assert sum(v["n"] for v in result["calibration_bins"]) == 2
    assert result["observed_blue_win_rate"] == .5


def test_metrics_single_outcome_and_empty_cohorts_are_honest():
    result = metrics([1, 1], [.4, .6])
    assert result["roc_auc"] is None
    assert result["accuracy"] == .5
    assert metrics([], []) == {"n": 0}


@pytest.mark.parametrize("probabilities", [[-.1, .5], [.5, 1.1], [np.nan, .5], [np.inf, .5]])
def test_metrics_reject_invalid_probability(probabilities):
    with pytest.raises(ValueError, match="Invalid probability"):
        metrics([0, 1], probabilities)


def test_split_has_disjoint_games_and_strictly_ordered_dates():
    frame, config = split_fixture()
    parts = temporal_split(frame.sample(frac=1, random_state=19), config)
    identifiers = [set(v.game_id) for v in parts.values()]
    assert len(set.union(*identifiers)) == len(frame)
    for i, a in enumerate(identifiers):
        for b in identifiers[i + 1:]:
            assert not a & b
    for a, b in zip(list(parts.values()), list(parts.values())[1:]):
        assert a.date.max() < b.date.min()
    for name, end_key in zip(parts, ("train_end", "validation_end", "calibration_end", "as_of")):
        assert (parts[name].available_at < pd.Timestamp(config[end_key])).all()


def test_timestamp_boundary_remains_one_partition_and_late_labels_are_purged():
    frame, config = split_fixture()
    cutoff = pd.Timestamp(config["train_end"])
    extra = pd.DataFrame([
        {"game_id": "at-boundary-0", "date": cutoff, "available_at": cutoff + pd.Timedelta(hours=1), "blue_win": 0},
        {"game_id": "at-boundary-1", "date": cutoff, "available_at": cutoff + pd.Timedelta(hours=1), "blue_win": 1},
        {"game_id": "late-train-label", "date": cutoff - pd.Timedelta(hours=1), "available_at": cutoff, "blue_win": 1},
    ])
    parts = temporal_split(pd.concat([frame, extra]), config)
    assert {"at-boundary-0", "at-boundary-1"} <= set(parts["validation"].game_id)
    assert "late-train-label" not in set(pd.concat(parts.values()).game_id)


def test_split_rejects_duplicate_games_instead_of_leaking_participants():
    frame, config = split_fixture()
    with pytest.raises(ValueError, match="Duplicate game_id"):
        temporal_split(pd.concat([frame, frame.iloc[[0]]]), config)


@pytest.mark.parametrize("replacement", ["2024-02-01", "2024-04-02T00:00:00Z"])
def test_split_rejects_ambiguous_or_nonmonotonic_cutoffs(replacement):
    frame, config = split_fixture()
    config["validation_end"] = replacement
    with pytest.raises(ValueError, match="strictly increasing timezone-aware"):
        temporal_split(frame, config)


def test_split_requires_sufficient_samples_and_both_outcomes():
    frame, config = split_fixture()
    config["min_train"] = 50
    with pytest.raises(ValueError, match="Insufficient real data in train"):
        temporal_split(frame, config)
    config["min_train"] = 2
    frame.loc[frame.date < pd.Timestamp(config["train_end"]), "blue_win"] = 1
    with pytest.raises(ValueError, match="both outcomes"):
        temporal_split(frame, config)


def test_paired_bootstrap_point_is_raw_loss_difference_and_reproducible():
    y = np.array([0, 1, 0, 1, 0, 1])
    b = np.array([.4, .6, .3, .7, .45, .55])
    c = np.array([.2, .8, .4, .6, .3, .7])
    days = pd.Series(pd.to_datetime(["2024-01-01"] * 2 + ["2024-01-02"] * 2 + ["2024-01-03"] * 2, utc=True))
    first = paired_day_bootstrap(y, b, c, days, seed=123, repetitions=100)
    second = paired_day_bootstrap(y, b, c, days, seed=123, repetitions=100)
    assert first == second
    assert first["point"] == pytest.approx(log_loss(y, c) - log_loss(y, b))
    assert first["days"] == 3
    assert first["point"] < 0
    equal = paired_day_bootstrap(y, b, b, days, repetitions=100)
    assert equal["point"] == 0
    assert equal["day_block_bootstrap_95_interval"] == [0.0, 0.0]
