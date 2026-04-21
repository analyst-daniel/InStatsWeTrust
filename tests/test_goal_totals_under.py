from app.strategy.goal_totals_under import (
    GoalTotalsUnderInput,
    TotalSideType,
    UnderTimeBucket,
    build_goal_totals_under_input,
    goal_totals_under_activation_decision,
    goal_totals_under_enter_decision_pre_stability_v1,
    goal_totals_under_enter_decision_v1,
    parse_totals_market,
)


def test_parse_totals_market_under() -> None:
    parsed = parse_totals_market("Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5", "Under")
    assert parsed.valid is True
    assert parsed.line == 3.5
    assert parsed.selected_side_type == TotalSideType.UNDER


def test_parse_totals_market_over() -> None:
    parsed = parse_totals_market("Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5", "Over")
    assert parsed.valid is True
    assert parsed.line == 3.5
    assert parsed.selected_side_type == TotalSideType.OVER


def test_parse_totals_market_invalid_for_non_totals_question() -> None:
    parsed = parse_totals_market("Will Cerezo Osaka win on 2026-04-19?", "Under")
    assert parsed.valid is False
    assert parsed.selected_side_type == TotalSideType.UNKNOWN


def test_build_goal_totals_under_input_populates_buffer() -> None:
    data = build_goal_totals_under_input(
        event_id="1",
        event_slug="j1-cer-kyo-2026-04-19-more-markets",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC - More Markets",
        market_id="m1",
        market_slug="j1-cer-kyo-2026-04-19-ou-3pt5",
        question="Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5",
        side="Under",
        minute=78.0,
        score="2-0",
        home_team="Cerezo Osaka",
        away_team="Kyoto Sanga FC",
        data_confidence_flag=True,
    )
    assert data.home_goals == 2
    assert data.away_goals == 0
    assert data.total_goals == 2
    assert data.total_line == 3.5
    assert data.goal_buffer == 1.5
    assert data.selected_side_type == TotalSideType.UNDER
    assert data.within_activation_window is True
    assert data.time_bucket == UnderTimeBucket.MIN_75_85
    assert data.is_under_side is True
    assert data.parsed_totals_valid is True


def test_build_goal_totals_under_input_marks_outside_window_for_89() -> None:
    data = build_goal_totals_under_input(
        event_id="1",
        event_slug="j1-cer-kyo-2026-04-19-more-markets",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC - More Markets",
        market_id="m1",
        market_slug="j1-cer-kyo-2026-04-19-ou-2pt5",
        question="Cerezo Osaka vs Kyoto Sanga FC: O/U 2.5",
        side="Under",
        minute=89.0,
        score="1-0",
        home_team="Cerezo Osaka",
        away_team="Kyoto Sanga FC",
        data_confidence_flag=True,
    )
    assert data.within_activation_window is False
    assert data.time_bucket == UnderTimeBucket.OUTSIDE


def test_build_goal_totals_under_input_keeps_over_but_not_under() -> None:
    data = build_goal_totals_under_input(
        event_id="1",
        event_slug="j1-cer-kyo-2026-04-19-more-markets",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC - More Markets",
        market_id="m1",
        market_slug="j1-cer-kyo-2026-04-19-ou-4pt5",
        question="Cerezo Osaka vs Kyoto Sanga FC: O/U 4.5",
        side="Over",
        minute=74.0,
        score="1-0",
        home_team="Cerezo Osaka",
        away_team="Kyoto Sanga FC",
        data_confidence_flag=True,
    )
    assert data.selected_side_type == TotalSideType.OVER
    assert data.is_under_side is False
    assert data.time_bucket == UnderTimeBucket.MIN_70_74


def test_goal_totals_input_handles_missing_score() -> None:
    data = build_goal_totals_under_input(
        event_id="1",
        event_slug="j1-cer-kyo-2026-04-19-more-markets",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC - More Markets",
        market_id="m1",
        market_slug="j1-cer-kyo-2026-04-19-ou-4pt5",
        question="Cerezo Osaka vs Kyoto Sanga FC: O/U 4.5",
        side="Under",
        minute=74.0,
        score="",
        home_team="Cerezo Osaka",
        away_team="Kyoto Sanga FC",
        data_confidence_flag=False,
    )
    assert data.total_goals is None
    assert data.goal_buffer is None


def make_under_input(**overrides) -> GoalTotalsUnderInput:
    payload = {
        "event_id": "1",
        "event_slug": "j1-cer-kyo-2026-04-19-more-markets",
        "event_title": "Cerezo Osaka vs. Kyoto Sanga FC - More Markets",
        "market_id": "m1",
        "market_slug": "j1-cer-kyo-2026-04-19-ou-3pt5",
        "question": "Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5",
        "side": "Under",
        "minute": 78.0,
        "score": "2-0",
        "home_team": "Cerezo Osaka",
        "away_team": "Kyoto Sanga FC",
        "home_goals": 2,
        "away_goals": 0,
        "total_goals": 2,
        "total_line": 3.5,
        "goal_buffer": 1.5,
        "selected_side_type": TotalSideType.UNDER,
        "data_confidence_flag": True,
        "red_card_flag": False,
        "red_card_in_last_10min": False,
        "shots_last_10": 2,
        "shots_on_target_last_10": 0,
        "dangerous_attacks_last_10": 4,
        "corners_last_10": 1,
        "total_shots_both_last_10": 2,
        "total_dangerous_attacks_both_last_10": 6,
        "total_corners_both_last_10": 1,
        "goal_in_last_3min": False,
        "goal_in_last_5min": False,
        "pressure_trend_last_10": "stable",
        "shots_trend_last_10": "stable",
        "dangerous_attacks_trend_last_10": "stable",
        "tempo_change_last_10": "stable",
        "stable_for_2_snapshots": True,
        "stable_for_3_snapshots": False,
    }
    payload.update(overrides)
    return GoalTotalsUnderInput(**payload)


def test_goal_totals_under_activation_accepts_valid_under_case() -> None:
    decision = goal_totals_under_activation_decision(make_under_input())
    assert decision.active is True
    assert decision.reason == "goal_totals_under_activation_ok_75_85"


def test_goal_totals_under_activation_rejects_over_side() -> None:
    decision = goal_totals_under_activation_decision(
        make_under_input(side="Over", selected_side_type=TotalSideType.OVER)
    )
    assert decision.active is False
    assert decision.reason == "goal_totals_under_wrong_side"


def test_goal_totals_under_activation_rejects_buffer_below_one() -> None:
    decision = goal_totals_under_activation_decision(
        make_under_input(score="3-0", home_goals=3, away_goals=0, total_goals=3, goal_buffer=0.5)
    )
    assert decision.active is False
    assert decision.reason == "goal_totals_under_buffer_too_small"


def test_goal_totals_under_activation_rejects_red_card_flag() -> None:
    decision = goal_totals_under_activation_decision(make_under_input(red_card_flag=True))
    assert decision.active is False
    assert decision.reason == "goal_totals_under_red_card"


def test_goal_totals_under_activation_rejects_recent_red_card() -> None:
    decision = goal_totals_under_activation_decision(make_under_input(red_card_in_last_10min=True))
    assert decision.active is False
    assert decision.reason == "goal_totals_under_red_card"


def test_goal_totals_under_activation_rejects_low_confidence() -> None:
    decision = goal_totals_under_activation_decision(make_under_input(data_confidence_flag=False))
    assert decision.active is False
    assert decision.reason == "goal_totals_under_low_data_confidence"


def test_goal_totals_under_activation_rejects_minute_outside_window() -> None:
    decision = goal_totals_under_activation_decision(make_under_input(minute=89.0))
    assert decision.active is False
    assert decision.reason == "goal_totals_under_minute_outside_window"


def test_goal_totals_under_activation_marks_70_74_bucket() -> None:
    decision = goal_totals_under_activation_decision(make_under_input(minute=72.0))
    assert decision.active is True
    assert decision.reason == "goal_totals_under_activation_ok_70_74"


def test_goal_totals_under_activation_marks_86_88_bucket() -> None:
    decision = goal_totals_under_activation_decision(make_under_input(minute=87.0))
    assert decision.active is True
    assert decision.reason == "goal_totals_under_activation_ok_86_88"


def test_goal_totals_under_pre_stability_accepts_valid_under_case() -> None:
    decision = goal_totals_under_enter_decision_pre_stability_v1(make_under_input())
    assert decision.enter is True
    assert decision.reason == "goal_totals_under_pre_stability_ok"


def test_goal_totals_under_enter_accepts_valid_under_case() -> None:
    decision = goal_totals_under_enter_decision_v1(make_under_input())
    assert decision.enter is True
    assert decision.reason == "goal_totals_under_enter"


def test_goal_totals_under_enter_rejects_recent_goal() -> None:
    decision = goal_totals_under_enter_decision_v1(make_under_input(goal_in_last_3min=True))
    assert decision.enter is False
    assert decision.reason == "goal_totals_under_no_enter_recent_goal"


def test_goal_totals_under_enter_rejects_pressure() -> None:
    decision = goal_totals_under_enter_decision_v1(make_under_input(shots_last_10=4))
    assert decision.enter is False
    assert decision.reason == "goal_totals_under_no_enter_pressure"


def test_goal_totals_under_enter_rejects_shots_on_target_pressure() -> None:
    decision = goal_totals_under_enter_decision_v1(make_under_input(shots_on_target_last_10=1))
    assert decision.enter is False
    assert decision.reason == "goal_totals_under_no_enter_pressure"


def test_goal_totals_under_enter_rejects_chaos() -> None:
    decision = goal_totals_under_enter_decision_v1(make_under_input(total_shots_both_last_10=4))
    assert decision.enter is False
    assert decision.reason == "goal_totals_under_no_enter_chaos"


def test_goal_totals_under_enter_rejects_rising_tempo() -> None:
    decision = goal_totals_under_enter_decision_v1(make_under_input(tempo_change_last_10="up"))
    assert decision.enter is False
    assert decision.reason == "goal_totals_under_no_enter_chaos"


def test_goal_totals_under_enter_rejects_not_stable() -> None:
    decision = goal_totals_under_enter_decision_v1(
        make_under_input(stable_for_2_snapshots=False, stable_for_3_snapshots=False)
    )
    assert decision.enter is False
    assert decision.reason == "goal_totals_under_no_enter_not_stable"


def test_goal_totals_under_enter_allows_slightly_looser_case_for_buffer_two_plus() -> None:
    decision = goal_totals_under_enter_decision_v1(
        make_under_input(
            score="1-0",
            home_goals=1,
            away_goals=0,
            total_goals=1,
            total_line=3.5,
            goal_buffer=2.5,
            shots_last_10=3,
            shots_on_target_last_10=1,
            corners_last_10=2,
            dangerous_attacks_last_10=7,
            total_shots_both_last_10=5,
            total_dangerous_attacks_both_last_10=10,
            total_corners_both_last_10=3,
        )
    )
    assert decision.enter is True
    assert decision.reason == "goal_totals_under_enter"
