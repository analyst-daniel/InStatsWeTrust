from app.strategy.spread_confirmation import (
    SpreadSideType,
    spread_minus_activation_decision,
    spread_minus_enter_decision_v1,
    spread_plus_activation_decision,
    spread_plus_enter_decision_v1,
    SpreadTimeBucket,
    SpreadConfirmationInput,
    build_spread_input,
    parse_spread_market,
)


def test_parse_spread_market_for_listed_team_side() -> None:
    parsed = parse_spread_market("Spread: Iwaki FC (-2.5)", "Iwaki FC")
    assert parsed.valid is True
    assert parsed.listed_team == "Iwaki FC"
    assert parsed.line == -2.5
    assert parsed.side_type == SpreadSideType.MINUS
    assert parsed.selected_team == "Iwaki FC"
    assert parsed.selected_line == -2.5
    assert parsed.selected_side_type == SpreadSideType.MINUS


def test_parse_spread_market_for_opposite_side() -> None:
    parsed = parse_spread_market("Spread: Iwaki FC (-2.5)", "AC Nagano Parceiro")
    assert parsed.valid is True
    assert parsed.listed_team == "Iwaki FC"
    assert parsed.line == -2.5
    assert parsed.selected_team == "AC Nagano Parceiro"
    assert parsed.selected_line == 2.5
    assert parsed.selected_side_type == SpreadSideType.PLUS


def test_parse_spread_market_returns_invalid_for_non_spread_question() -> None:
    parsed = parse_spread_market("Will Iwaki FC win on 2026-04-19?", "Yes")
    assert parsed.valid is False
    assert parsed.side_type == SpreadSideType.UNKNOWN
    assert parsed.selected_side_type == SpreadSideType.UNKNOWN


def test_build_spread_input_populates_score_and_leader_context() -> None:
    data = build_spread_input(
        event_id="1",
        event_slug="j2-iwa-nag-2026-04-19-more-markets",
        event_title="Iwaki FC vs. AC Nagano Parceiro - More Markets",
        market_id="m1",
        market_slug="j2-iwa-nag-2026-04-19-spread-home-2pt5",
        question="Spread: Iwaki FC (-2.5)",
        side="AC Nagano Parceiro",
        minute=81.0,
        score="1-0",
        home_team="Iwaki FC",
        away_team="AC Nagano Parceiro",
        data_confidence_flag=True,
    )
    assert data.home_goals == 1
    assert data.away_goals == 0
    assert data.goal_difference == 1
    assert data.leader_team == "Iwaki FC"
    assert data.trailing_team == "AC Nagano Parceiro"
    assert data.spread_team == "Iwaki FC"
    assert data.spread_line == -2.5
    assert data.spread_side_type == SpreadSideType.MINUS
    assert data.selected_team == "AC Nagano Parceiro"
    assert data.selected_line == 2.5
    assert data.selected_side_type == SpreadSideType.PLUS
    assert data.time_bucket == SpreadTimeBucket.MIN_81_85
    assert data.within_analysis_window is True
    assert data.parsed_spread_valid is True


def test_build_spread_input_marks_outside_window_for_89() -> None:
    data = build_spread_input(
        event_id="1",
        event_slug="j2-iwa-nag-2026-04-19-more-markets",
        event_title="Iwaki FC vs. AC Nagano Parceiro - More Markets",
        market_id="m1",
        market_slug="j2-iwa-nag-2026-04-19-spread-home-2pt5",
        question="Spread: Iwaki FC (-1.5)",
        side="Iwaki FC",
        minute=89.0,
        score="2-0",
        home_team="Iwaki FC",
        away_team="AC Nagano Parceiro",
        data_confidence_flag=True,
    )
    assert data.time_bucket == SpreadTimeBucket.OUTSIDE
    assert data.within_analysis_window is False


def make_plus_input(**overrides) -> SpreadConfirmationInput:
    payload = {
        "event_id": "1",
        "event_slug": "j2-iwa-nag-2026-04-19-more-markets",
        "event_title": "Iwaki FC vs. AC Nagano Parceiro - More Markets",
        "market_id": "m1",
        "market_slug": "j2-iwa-nag-2026-04-19-spread-home-1pt5",
        "question": "Spread: Iwaki FC (-1.5)",
        "side": "AC Nagano Parceiro",
        "minute": 81.0,
        "score": "1-0",
        "home_team": "Iwaki FC",
        "away_team": "AC Nagano Parceiro",
        "home_goals": 1,
        "away_goals": 0,
        "goal_difference": 1,
        "leader_team": "Iwaki FC",
        "trailing_team": "AC Nagano Parceiro",
        "spread_team": "Iwaki FC",
        "spread_line": -1.5,
        "spread_side_type": SpreadSideType.MINUS,
        "selected_team": "AC Nagano Parceiro",
        "selected_line": 1.5,
        "selected_side_type": SpreadSideType.PLUS,
        "data_confidence_flag": True,
        "leader_red_card": False,
        "trailing_red_card": False,
        "leader_shots_last_10": 2,
        "leader_shots_on_target_last_10": 0,
        "leader_dangerous_attacks_last_10": 4,
        "leader_corners_last_10": 1,
        "underdog_shots_last_10": 1,
        "underdog_shots_on_target_last_10": 0,
        "underdog_dangerous_attacks_last_10": 2,
        "underdog_corners_last_10": 0,
        "goal_in_last_3min": False,
        "red_card_in_last_10min": False,
        "tempo_change_last_10": "stable",
        "leader_pressure_trend_last_10": "stable",
        "stable_for_2_snapshots": True,
        "stable_for_3_snapshots": False,
    }
    payload.update(overrides)
    return SpreadConfirmationInput(**payload)


def test_spread_plus_activation_accepts_valid_plus_side() -> None:
    decision = spread_plus_activation_decision(make_plus_input())
    assert decision.active is True
    assert decision.reason == "spread_plus_activation_ok"


def test_spread_plus_activation_accepts_plus_three_point_five() -> None:
    decision = spread_plus_activation_decision(
        make_plus_input(
            question="Spread: Iwaki FC (-3.5)",
            spread_line=-3.5,
            selected_line=3.5,
            score="3-0",
            home_goals=3,
            away_goals=0,
            goal_difference=3,
        )
    )
    assert decision.active is True
    assert decision.reason == "spread_plus_activation_ok"


def test_spread_plus_activation_accepts_plus_four_point_five() -> None:
    decision = spread_plus_activation_decision(
        make_plus_input(
            question="Spread: Iwaki FC (-4.5)",
            spread_line=-4.5,
            selected_line=4.5,
            score="4-0",
            home_goals=4,
            away_goals=0,
            goal_difference=4,
        )
    )
    assert decision.active is True
    assert decision.reason == "spread_plus_activation_ok"


def test_spread_plus_activation_rejects_score_outside_handicap_range() -> None:
    decision = spread_plus_activation_decision(make_plus_input(score="2-0", home_goals=2, away_goals=0, goal_difference=2))
    assert decision.active is False
    assert decision.reason == "spread_plus_score_outside_handicap_range"


def test_spread_plus_enter_accepts_lively_underdog_case() -> None:
    decision = spread_plus_enter_decision_v1(make_plus_input())
    assert decision.enter is True
    assert decision.reason == "spread_plus_enter"


def test_spread_plus_enter_rejects_dead_underdog() -> None:
    decision = spread_plus_enter_decision_v1(
        make_plus_input(
            underdog_shots_last_10=0,
            underdog_shots_on_target_last_10=0,
            underdog_dangerous_attacks_last_10=0,
            underdog_corners_last_10=0,
        )
    )
    assert decision.enter is False
    assert decision.reason == "spread_plus_no_enter_underdog_not_alive"


def test_spread_plus_enter_rejects_favorite_dominating() -> None:
    decision = spread_plus_enter_decision_v1(make_plus_input(leader_shots_on_target_last_10=2))
    assert decision.enter is False
    assert decision.reason == "spread_plus_no_enter_favorite_dominating"


def test_spread_plus_enter_rejects_not_stable() -> None:
    decision = spread_plus_enter_decision_v1(make_plus_input(stable_for_2_snapshots=False, stable_for_3_snapshots=False))
    assert decision.enter is False
    assert decision.reason == "spread_plus_no_enter_not_stable"


def make_minus_input(**overrides) -> SpreadConfirmationInput:
    payload = {
        "event_id": "1",
        "event_slug": "j2-iwa-nag-2026-04-19-more-markets",
        "event_title": "Iwaki FC vs. AC Nagano Parceiro - More Markets",
        "market_id": "m1",
        "market_slug": "j2-iwa-nag-2026-04-19-spread-home-1pt5",
        "question": "Spread: Iwaki FC (-1.5)",
        "side": "Iwaki FC",
        "minute": 81.0,
        "score": "2-0",
        "home_team": "Iwaki FC",
        "away_team": "AC Nagano Parceiro",
        "home_goals": 2,
        "away_goals": 0,
        "goal_difference": 2,
        "leader_team": "Iwaki FC",
        "trailing_team": "AC Nagano Parceiro",
        "spread_team": "Iwaki FC",
        "spread_line": -1.5,
        "spread_side_type": SpreadSideType.MINUS,
        "selected_team": "Iwaki FC",
        "selected_line": -1.5,
        "selected_side_type": SpreadSideType.MINUS,
        "data_confidence_flag": True,
        "leader_red_card": False,
        "trailing_red_card": False,
        "leader_shots_last_10": 2,
        "leader_shots_on_target_last_10": 1,
        "leader_dangerous_attacks_last_10": 4,
        "leader_corners_last_10": 1,
        "underdog_shots_last_10": 1,
        "underdog_shots_on_target_last_10": 0,
        "underdog_dangerous_attacks_last_10": 2,
        "underdog_corners_last_10": 0,
        "goal_in_last_3min": False,
        "red_card_in_last_10min": False,
        "tempo_change_last_10": "stable",
        "underdog_pressure_trend_last_10": "stable",
        "stable_for_2_snapshots": True,
        "stable_for_3_snapshots": False,
    }
    payload.update(overrides)
    return SpreadConfirmationInput(**payload)


def test_spread_minus_activation_accepts_valid_minus_side() -> None:
    decision = spread_minus_activation_decision(make_minus_input())
    assert decision.active is True
    assert decision.reason == "spread_minus_activation_ok"


def test_spread_minus_activation_accepts_minus_three_point_five_at_four_zero() -> None:
    decision = spread_minus_activation_decision(
        make_minus_input(
            question="Spread: Iwaki FC (-3.5)",
            spread_line=-3.5,
            selected_line=-3.5,
            score="4-0",
            home_goals=4,
            away_goals=0,
            goal_difference=4,
        )
    )
    assert decision.active is True
    assert decision.reason == "spread_minus_activation_ok"


def test_spread_minus_activation_accepts_minus_four_point_five_at_five_zero() -> None:
    decision = spread_minus_activation_decision(
        make_minus_input(
            question="Spread: Iwaki FC (-4.5)",
            spread_line=-4.5,
            selected_line=-4.5,
            score="5-0",
            home_goals=5,
            away_goals=0,
            goal_difference=5,
        )
    )
    assert decision.active is True
    assert decision.reason == "spread_minus_activation_ok"


def test_spread_minus_activation_rejects_minus_one_point_five_at_one_zero() -> None:
    decision = spread_minus_activation_decision(
        make_minus_input(score="1-0", home_goals=1, away_goals=0, goal_difference=1)
    )
    assert decision.active is False
    assert decision.reason == "spread_minus_margin_too_small"


def test_spread_minus_activation_rejects_minus_two_point_five_at_two_zero() -> None:
    decision = spread_minus_activation_decision(
        make_minus_input(
            question="Spread: Iwaki FC (-2.5)",
            spread_line=-2.5,
            selected_line=-2.5,
            score="2-0",
            home_goals=2,
            away_goals=0,
            goal_difference=2,
        )
    )
    assert decision.active is False
    assert decision.reason == "spread_minus_margin_too_small"


def test_spread_minus_activation_rejects_minus_three_point_five_at_three_zero() -> None:
    decision = spread_minus_activation_decision(
        make_minus_input(
            question="Spread: Iwaki FC (-3.5)",
            spread_line=-3.5,
            selected_line=-3.5,
            score="3-0",
            home_goals=3,
            away_goals=0,
            goal_difference=3,
        )
    )
    assert decision.active is False
    assert decision.reason == "spread_minus_margin_too_small"


def test_spread_minus_activation_rejects_minus_four_point_five_at_four_zero() -> None:
    decision = spread_minus_activation_decision(
        make_minus_input(
            question="Spread: Iwaki FC (-4.5)",
            spread_line=-4.5,
            selected_line=-4.5,
            score="4-0",
            home_goals=4,
            away_goals=0,
            goal_difference=4,
        )
    )
    assert decision.active is False
    assert decision.reason == "spread_minus_margin_too_small"


def test_spread_minus_enter_accepts_controlled_margin_case() -> None:
    decision = spread_minus_enter_decision_v1(make_minus_input())
    assert decision.enter is True
    assert decision.reason == "spread_minus_enter"


def test_spread_minus_enter_rejects_when_underdog_presses_too_much() -> None:
    decision = spread_minus_enter_decision_v1(make_minus_input(underdog_shots_on_target_last_10=2))
    assert decision.enter is False
    assert decision.reason == "spread_minus_no_enter_pressure"


def test_spread_minus_enter_rejects_when_leader_not_in_control() -> None:
    decision = spread_minus_enter_decision_v1(
        make_minus_input(
            leader_shots_last_10=0,
            leader_shots_on_target_last_10=0,
            leader_dangerous_attacks_last_10=0,
            leader_corners_last_10=0,
        )
    )
    assert decision.enter is False
    assert decision.reason == "spread_minus_no_enter_leader_not_in_control"


def test_spread_minus_enter_rejects_not_stable() -> None:
    decision = spread_minus_enter_decision_v1(make_minus_input(stable_for_2_snapshots=False, stable_for_3_snapshots=False))
    assert decision.enter is False
    assert decision.reason == "spread_minus_no_enter_not_stable"
