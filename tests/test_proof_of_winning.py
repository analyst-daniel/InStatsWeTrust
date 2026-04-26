from app.strategy.proof_of_winning import (
    ProofOfWinningInput,
    TimeBucket,
    TrendState,
    activation_decision,
    enter_decision_v1,
)


def make_input(**overrides) -> ProofOfWinningInput:
    payload = {
        "event_id": "296790",
        "event_slug": "j1100-cer-kyo-2026-04-18-more-markets",
        "event_title": "Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        "market_id": "1674823",
        "market_slug": "j1100-cer-kyo-2026-04-18-cerezo-win",
        "question": "Will Cerezo Osaka win on 2026-04-18?",
        "side": "Yes",
        "minute": 78.0,
        "score": "2-0",
        "goal_difference": 2,
        "leader_team": "Cerezo Osaka",
        "trailing_team": "Kyoto Sanga FC",
        "leader_red_card": False,
        "trailing_red_card": False,
        "data_confidence_flag": True,
        "shots_last_5": 0,
        "shots_on_target_last_5": 0,
        "shots_last_10": 1,
        "shots_on_target_last_10": 0,
        "dangerous_attacks_last_5": 1,
        "dangerous_attacks_last_10": 2,
        "corners_last_5": 0,
        "corners_last_10": 1,
        "total_shots_both_last_10": 2,
        "total_dangerous_attacks_both_last_10": 4,
        "total_corners_both_last_10": 1,
        "pressure_trend_last_10": TrendState.STABLE,
        "shots_trend_last_10": TrendState.STABLE,
        "dangerous_attacks_trend_last_10": TrendState.STABLE,
        "tempo_change_last_10": TrendState.STABLE,
        "stable_for_2_snapshots": True,
        "stable_for_3_snapshots": False,
        "source_fields_present": [
            "shots_last_5",
            "shots_last_10",
            "shots_on_target_last_10",
            "dangerous_attacks_last_10",
            "corners_last_10",
        ],
    }
    payload.update(overrides)
    return ProofOfWinningInput(**payload)


def test_activation_accepts_valid_input_inside_window() -> None:
    data = make_input()
    decision = activation_decision(data)
    assert decision.active is True
    assert decision.reason == "proof_of_winning_activation_ok"
    assert data.time_bucket == TimeBucket.MIN_75_80


def test_activation_accepts_minute_72_inside_window() -> None:
    data = make_input(minute=72.0)
    decision = activation_decision(data)
    assert decision.active is True
    assert decision.reason == "proof_of_winning_activation_ok"
    assert data.time_bucket == TimeBucket.MIN_70_74


def test_activation_rejects_minute_89_and_later() -> None:
    data = make_input(minute=89.0)
    decision = activation_decision(data)
    assert decision.active is False
    assert decision.reason == "proof_of_winning_minute_outside_window"


def test_activation_rejects_goal_difference_below_two() -> None:
    data = make_input(goal_difference=1, score="1-0")
    decision = activation_decision(data)
    assert decision.active is False
    assert decision.reason == "proof_of_winning_goal_difference_too_low"


def test_activation_rejects_red_card_for_leader() -> None:
    data = make_input(leader_red_card=True)
    decision = activation_decision(data)
    assert decision.active is False
    assert decision.reason == "proof_of_winning_leader_red_card"


def test_activation_rejects_when_required_metrics_missing() -> None:
    data = make_input(source_fields_present=["shots_last_5", "shots_last_10"])
    decision = activation_decision(data)
    assert decision.active is False
    assert decision.reason == "proof_of_winning_missing_required_fields"


def test_enter_decision_accepts_low_pressure_stable_case() -> None:
    data = make_input(stable_for_2_snapshots=True)
    decision = enter_decision_v1(data)
    assert decision.enter is True
    assert decision.reason == "proof_of_winning_enter"


def test_enter_decision_rejects_high_pressure_case() -> None:
    data = make_input(shots_last_10=4, stable_for_2_snapshots=True)
    decision = enter_decision_v1(data)
    assert decision.enter is False
    assert decision.reason == "proof_of_winning_no_enter_pressure_shots_last_10"


def test_enter_decision_rejects_upward_trend() -> None:
    data = make_input(pressure_trend_last_10=TrendState.UP, stable_for_2_snapshots=True)
    decision = enter_decision_v1(data)
    assert decision.enter is False
    assert decision.reason == "proof_of_winning_no_enter_trend_pressure_up"


def test_enter_decision_rejects_chaos_goal_last_3min() -> None:
    data = make_input(goal_in_last_3min=True, stable_for_2_snapshots=True)
    decision = enter_decision_v1(data)
    assert decision.enter is False
    assert decision.reason == "proof_of_winning_no_enter_chaos_goal_last_3min"


def test_enter_decision_rejects_when_not_stable() -> None:
    data = make_input(stable_for_2_snapshots=False, stable_for_3_snapshots=False)
    decision = enter_decision_v1(data)
    assert decision.enter is False
    assert decision.reason == "proof_of_winning_no_enter_not_stable"
