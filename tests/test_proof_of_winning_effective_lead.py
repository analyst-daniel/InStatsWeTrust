from app.strategy.proof_of_winning import ProofOfWinningInput
from app.strategy.proof_of_winning_effective_lead import (
    effective_goal_difference_from_detail,
    populate_input_with_effective_goal_difference,
)


def detail_with_goals(home_goals, away_goals, events):
    return {
        "fixture": {
            "fixture": {"id": 12345, "status": {"short": "2H", "elapsed": 78}},
            "teams": {"home": {"name": "Cerezo Osaka"}, "away": {"name": "Kyoto Sanga FC"}},
            "goals": {"home": home_goals, "away": away_goals},
        },
        "events": events,
    }


def goal_event(minute: int, team: str, detail: str = "Normal Goal") -> dict:
    return {
        "time": {"elapsed": minute, "extra": None},
        "team": {"name": team},
        "type": "Goal",
        "detail": detail,
    }


def test_effective_goal_difference_penalizes_early_penalty_goal() -> None:
    payload = detail_with_goals(
        2,
        0,
        [
            goal_event(12, "Cerezo Osaka", "Penalty"),
            goal_event(55, "Cerezo Osaka", "Normal Goal"),
        ],
    )
    result = effective_goal_difference_from_detail(payload)
    assert result.data_confidence_flag is True
    assert result.effective_goal_difference is not None
    assert result.effective_goal_difference < 2.0


def test_effective_goal_difference_rewards_late_two_goal_kill_sequence() -> None:
    payload = detail_with_goals(
        2,
        0,
        [
            goal_event(76, "Cerezo Osaka", "Normal Goal"),
            goal_event(79, "Cerezo Osaka", "Normal Goal"),
        ],
    )
    result = effective_goal_difference_from_detail(payload)
    assert result.data_confidence_flag is True
    assert result.effective_goal_difference is not None
    assert result.effective_goal_difference > 2.0


def test_effective_goal_difference_can_be_injected_into_input() -> None:
    payload = detail_with_goals(
        2,
        0,
        [
            goal_event(31, "Cerezo Osaka", "Normal Goal"),
            goal_event(68, "Cerezo Osaka", "Normal Goal"),
        ],
    )
    result = effective_goal_difference_from_detail(payload)
    base = ProofOfWinningInput(
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id="1674823",
        market_slug="j1100-cer-kyo-2026-04-18-cerezo-win",
        question="Will Cerezo Osaka win on 2026-04-18?",
        side="Yes",
        minute=78.0,
        score="2-0",
        goal_difference=2,
        leader_team="Cerezo Osaka",
        trailing_team="Kyoto Sanga FC",
    )
    hydrated = populate_input_with_effective_goal_difference(base, result)
    assert hydrated.effective_goal_difference == result.effective_goal_difference
