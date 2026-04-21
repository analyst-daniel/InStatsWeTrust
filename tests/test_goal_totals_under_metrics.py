from app.strategy.goal_totals_under import GoalTotalsUnderInput, TotalSideType
from app.strategy.goal_totals_under_metrics import (
    build_goal_totals_under_rolling_metrics,
    populate_goal_totals_under_input_with_metrics,
)


def detail(saved_at: str, elapsed: int, home_goals: int, away_goals: int, home_stats: dict, away_stats: dict, events: list[dict]):
    return {
        "saved_at": saved_at,
        "fixture_id": "12345",
        "event_title": "Cerezo Osaka vs. Kyoto Sanga FC",
        "fixture": {
            "fixture": {"id": 12345, "status": {"short": "2H", "elapsed": elapsed}},
            "teams": {"home": {"name": "Cerezo Osaka"}, "away": {"name": "Kyoto Sanga FC"}},
            "goals": {"home": home_goals, "away": away_goals},
        },
        "statistics": [
            {"team": {"name": "Cerezo Osaka"}, "statistics": stats_payload(home_stats)},
            {"team": {"name": "Kyoto Sanga FC"}, "statistics": stats_payload(away_stats)},
        ],
        "events": events,
    }


def stats_payload(values: dict) -> list[dict]:
    return [
        {"type": "Total Shots", "value": values.get("shots", 0)},
        {"type": "Shots on Goal", "value": values.get("shots_on_target", 0)},
        {"type": "Corner Kicks", "value": values.get("corners", 0)},
        {"type": "Dangerous Attacks", "value": values.get("dangerous_attacks", 0)},
        {"type": "Attacks", "value": values.get("attacks", 0)},
    ]


def test_build_goal_totals_under_rolling_metrics_from_detail_history() -> None:
    history = [
        detail(
            "2026-04-19T08:20:00Z",
            68,
            2,
            0,
            {"shots": 4, "shots_on_target": 1, "corners": 1, "dangerous_attacks": 8, "attacks": 20},
            {"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 4, "attacks": 14},
            [{"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
        detail(
            "2026-04-19T08:25:00Z",
            73,
            2,
            0,
            {"shots": 5, "shots_on_target": 1, "corners": 1, "dangerous_attacks": 10, "attacks": 24},
            {"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 5, "attacks": 16},
            [{"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
        detail(
            "2026-04-19T08:30:00Z",
            78,
            2,
            0,
            {"shots": 5, "shots_on_target": 1, "corners": 1, "dangerous_attacks": 11, "attacks": 25},
            {"shots": 3, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 6, "attacks": 18},
            [{"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
    ]
    metrics = build_goal_totals_under_rolling_metrics(history)
    assert metrics.match.shots_last_10 == 2
    assert metrics.match.shots_on_target_last_10 == 0
    assert metrics.match.dangerous_attacks_last_10 == 5
    assert metrics.match.attacks_last_10 == 9
    assert metrics.match.corners_last_10 == 1
    assert metrics.totals.total_shots_both_last_10 == 2
    assert metrics.data_confidence_flag is True


def test_populate_goal_totals_under_input_with_metrics() -> None:
    history = [
        detail(
            "2026-04-19T08:20:00Z",
            68,
            2,
            0,
            {"shots": 4, "shots_on_target": 1, "corners": 1, "dangerous_attacks": 8, "attacks": 20},
            {"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 4, "attacks": 14},
            [],
        ),
        detail(
            "2026-04-19T08:25:00Z",
            73,
            2,
            0,
            {"shots": 5, "shots_on_target": 1, "corners": 1, "dangerous_attacks": 10, "attacks": 24},
            {"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 5, "attacks": 16},
            [],
        ),
        detail(
            "2026-04-19T08:30:00Z",
            78,
            2,
            0,
            {"shots": 5, "shots_on_target": 1, "corners": 1, "dangerous_attacks": 11, "attacks": 25},
            {"shots": 3, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 6, "attacks": 18},
            [],
        ),
    ]
    metrics = build_goal_totals_under_rolling_metrics(history)
    base = GoalTotalsUnderInput(
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
        home_goals=2,
        away_goals=0,
        total_goals=2,
        total_line=3.5,
        goal_buffer=1.5,
        selected_side_type=TotalSideType.UNDER,
        data_confidence_flag=False,
    )
    hydrated = populate_goal_totals_under_input_with_metrics(base, metrics)
    assert hydrated.shots_last_10 == 2
    assert hydrated.shots_on_target_last_10 == 0
    assert hydrated.dangerous_attacks_last_10 == 5
    assert hydrated.attacks_last_10 == 9
    assert hydrated.corners_last_10 == 1
    assert hydrated.total_shots_both_last_10 == 2
    assert hydrated.data_confidence_flag is True
