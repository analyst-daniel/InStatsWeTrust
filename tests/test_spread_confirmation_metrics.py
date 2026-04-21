from app.strategy.spread_confirmation import SpreadConfirmationInput
from app.strategy.spread_confirmation_metrics import build_spread_rolling_metrics, populate_spread_input_with_metrics


def detail(saved_at: str, elapsed: int, home_goals: int, away_goals: int, home_stats: dict, away_stats: dict, events: list[dict]):
    return {
        "saved_at": saved_at,
        "fixture_id": "12345",
        "event_title": "Iwaki FC vs. AC Nagano Parceiro",
        "fixture": {
            "fixture": {"id": 12345, "status": {"short": "2H", "elapsed": elapsed}},
            "teams": {"home": {"name": "Iwaki FC"}, "away": {"name": "AC Nagano Parceiro"}},
            "goals": {"home": home_goals, "away": away_goals},
        },
        "statistics": [
            {"team": {"name": "Iwaki FC"}, "statistics": stats_payload(home_stats)},
            {"team": {"name": "AC Nagano Parceiro"}, "statistics": stats_payload(away_stats)},
        ],
        "events": events,
    }


def stats_payload(values: dict) -> list[dict]:
    return [
        {"type": "Total Shots", "value": values.get("shots", 0)},
        {"type": "Shots on Goal", "value": values.get("shots_on_target", 0)},
        {"type": "Corner Kicks", "value": values.get("corners", 0)},
        {"type": "Dangerous Attacks", "value": values.get("dangerous_attacks", 0)},
    ]


def test_build_spread_rolling_metrics_from_detail_history() -> None:
    history = [
        detail(
            "2026-04-19T08:20:00Z",
            68,
            2,
            0,
            {"shots": 8, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 20},
            {"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 4},
            [{"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
        detail(
            "2026-04-19T08:25:00Z",
            73,
            2,
            0,
            {"shots": 10, "shots_on_target": 5, "corners": 4, "dangerous_attacks": 24},
            {"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 6},
            [{"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
        detail(
            "2026-04-19T08:30:00Z",
            78,
            2,
            0,
            {"shots": 11, "shots_on_target": 5, "corners": 4, "dangerous_attacks": 25},
            {"shots": 3, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 7},
            [{"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
    ]
    metrics = build_spread_rolling_metrics(history)
    assert metrics.leader.shots_last_10 == 3
    assert metrics.leader.dangerous_attacks_last_10 == 5
    assert metrics.underdog.shots_last_10 == 2
    assert metrics.underdog.corners_last_10 == 1
    assert metrics.match.total_shots_both_last_10 == 5
    assert metrics.trend.underdog_pressure_trend_last_10.value in {"stable", "down", "up"}
    assert metrics.data_confidence_flag is True


def test_populate_spread_input_with_metrics() -> None:
    history = [
        detail(
            "2026-04-19T08:20:00Z",
            68,
            2,
            0,
            {"shots": 8, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 20},
            {"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 4},
            [],
        ),
        detail(
            "2026-04-19T08:25:00Z",
            73,
            2,
            0,
            {"shots": 10, "shots_on_target": 5, "corners": 4, "dangerous_attacks": 24},
            {"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 6},
            [],
        ),
        detail(
            "2026-04-19T08:30:00Z",
            78,
            2,
            0,
            {"shots": 11, "shots_on_target": 5, "corners": 4, "dangerous_attacks": 25},
            {"shots": 3, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 7},
            [],
        ),
    ]
    metrics = build_spread_rolling_metrics(history)
    base = SpreadConfirmationInput(
        event_id="1",
        event_slug="j2-iwa-nag-2026-04-19-more-markets",
        event_title="Iwaki FC vs. AC Nagano Parceiro - More Markets",
        market_id="m1",
        market_slug="j2-iwa-nag-2026-04-19-spread-home-2pt5",
        question="Spread: Iwaki FC (-2.5)",
        side="AC Nagano Parceiro",
        minute=78.0,
        score="2-0",
        home_team="Iwaki FC",
        away_team="AC Nagano Parceiro",
        home_goals=2,
        away_goals=0,
        goal_difference=2,
        leader_team="Iwaki FC",
        trailing_team="AC Nagano Parceiro",
        spread_team="Iwaki FC",
        spread_line=-2.5,
        spread_side_type="minus",
        selected_team="AC Nagano Parceiro",
        selected_line=2.5,
        selected_side_type="plus",
    )
    hydrated = populate_spread_input_with_metrics(base, metrics)
    assert hydrated.leader_shots_last_10 == 3
    assert hydrated.underdog_shots_last_10 == 2
    assert hydrated.total_shots_both_last_10 == 5
    assert hydrated.data_confidence_flag is True
    assert "leader_shots_last_10" in hydrated.source_fields_present
