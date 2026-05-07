from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.strategy.no_draw_hold import NoDrawScoreHold, parse_wait_tiers
from tests.test_strategy import live, market, settings
from app.strategy.engine import StrategyEngine


def no_draw_observation(score: str = "2-0", elapsed: float = 80.0):
    draw_market = market().model_copy(
        update={
            "question": "Will Team A FC vs. Team B FC end in a draw?",
            "outcomes": ["Yes", "No"],
            "yes_token_id": "yes",
            "no_token_id": "no",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.96,
            "best_ask_no": 0.97,
        }
    )
    decisions = StrategyEngine(settings()).evaluate_market(draw_market, live(elapsed).model_copy(update={"score": score}))
    return next(d.observation for d in decisions if d.observation.side == "No")


def test_no_draw_score_hold_waits_on_first_two_goal_margin(tmp_path) -> None:
    hold = NoDrawScoreHold(tmp_path / "no_draw_hold.json", min_hold_seconds=300)

    confirmed, reason = hold.check(no_draw_observation("2-0"))

    assert not confirmed
    assert reason == "waiting_no_draw_score_hold_first_seen"


def test_no_draw_score_hold_allows_after_wait(tmp_path) -> None:
    hold = NoDrawScoreHold(tmp_path / "no_draw_hold.json", min_hold_seconds=300)
    obs = no_draw_observation("2-0")
    assert not hold.check(obs)[0]
    hold.state[hold.key(obs)]["first_seen_at"] = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()

    confirmed, reason = hold.check(obs)

    assert confirmed
    assert reason.startswith("no_draw_score_held_")


def test_no_draw_score_hold_resets_when_score_changes(tmp_path) -> None:
    hold = NoDrawScoreHold(tmp_path / "no_draw_hold.json", min_hold_seconds=300)
    obs_2_0 = no_draw_observation("2-0")
    assert not hold.check(obs_2_0)[0]
    hold.state[hold.key(obs_2_0)]["first_seen_at"] = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    assert hold.check(obs_2_0)[0]

    confirmed, reason = hold.check(no_draw_observation("3-1"))

    assert not confirmed
    assert reason == "waiting_no_draw_score_hold_first_seen"


def test_no_draw_score_hold_does_not_wait_after_elapsed_limit(tmp_path) -> None:
    hold = NoDrawScoreHold(tmp_path / "no_draw_hold.json", min_hold_seconds=300, max_elapsed_for_hold=75)

    confirmed, reason = hold.check(no_draw_observation("2-0", elapsed=87.0))

    assert confirmed
    assert reason == "no_draw_score_hold_elapsed_above_max"


def test_no_draw_score_hold_uses_elapsed_wait_tiers(tmp_path) -> None:
    hold = NoDrawScoreHold(
        tmp_path / "no_draw_hold.json",
        min_hold_seconds=0,
        wait_tiers=[(70, 75, 180), (75, 80, 120), (80, 85, 60), (85, 89, 60)],
    )

    assert hold.wait_seconds(72.0) == 180
    assert hold.wait_seconds(77.0) == 120
    assert hold.wait_seconds(82.0) == 60
    assert hold.wait_seconds(87.0) == 60

    confirmed, reason = hold.check(no_draw_observation("2-0", elapsed=87.0))

    assert not confirmed
    assert reason == "waiting_no_draw_score_hold_first_seen"


def test_parse_wait_tiers_ignores_invalid_rows() -> None:
    raw = [
        {"min_elapsed": 70, "max_elapsed": 75, "wait_seconds": 300},
        {"min_elapsed": "bad", "max_elapsed": 80, "wait_seconds": 240},
        "skip",
    ]

    assert parse_wait_tiers(raw) == [(70.0, 75.0, 300.0)]


def test_no_draw_score_hold_keeps_first_seen_wait_when_elapsed_moves_to_next_tier(tmp_path) -> None:
    hold = NoDrawScoreHold(
        tmp_path / "no_draw_hold.json",
        min_hold_seconds=0,
        wait_tiers=[(70, 75, 180), (75, 80, 120), (80, 85, 60), (85, 89, 60)],
    )
    obs = no_draw_observation("2-0", elapsed=74.0)
    assert not hold.check(obs)[0]
    hold.state[hold.key(obs)]["first_seen_at"] = (datetime.now(timezone.utc) - timedelta(seconds=150)).isoformat()

    confirmed, reason = hold.check(no_draw_observation("2-0", elapsed=76.0))

    assert not confirmed
    assert reason.startswith("waiting_no_draw_score_hold_")
