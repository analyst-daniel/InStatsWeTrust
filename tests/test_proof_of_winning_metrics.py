from app.strategy.proof_of_winning import ProofOfWinningInput, TrendState
from app.strategy.proof_of_winning_metrics import build_rolling_metrics, populate_input_with_metrics


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
    ]


def test_build_rolling_metrics_from_detail_history() -> None:
    history = [
        detail(
            "2026-04-18T08:20:00Z",
            68,
            2,
            0,
            {"shots": 8, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 22},
            {"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 5},
            [{"time": {"elapsed": 67, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
        detail(
            "2026-04-18T08:25:00Z",
            73,
            2,
            0,
            {"shots": 9, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 24},
            {"shots": 2, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 8},
            [{"time": {"elapsed": 67, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
        detail(
            "2026-04-18T08:30:00Z",
            78,
            2,
            0,
            {"shots": 9, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 25},
            {"shots": 3, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 9},
            [{"time": {"elapsed": 67, "extra": None}, "type": "Goal", "detail": "Normal Goal"}],
        ),
    ]
    metrics = build_rolling_metrics(history)
    assert metrics.trailing.shots_last_5 == 1
    assert metrics.trailing.shots_last_10 == 2
    assert metrics.trailing.shots_on_target_last_10 == 0
    assert metrics.trailing.corners_last_10 == 1
    assert metrics.trailing.dangerous_attacks_last_10 == 4
    assert metrics.match.total_shots_both_last_10 == 3
    assert metrics.match.goal_in_last_3min is False
    assert metrics.trend.shots_trend_last_10 == TrendState.STABLE
    assert metrics.trend.dangerous_attacks_trend_last_10 == TrendState.DOWN
    assert metrics.data_confidence_flag is True


def test_populate_input_with_metrics() -> None:
    history = [
        detail(
            "2026-04-18T08:20:00Z",
            68,
            2,
            0,
            {"shots": 8, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 22},
            {"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 5},
            [],
        ),
        detail(
            "2026-04-18T08:25:00Z",
            73,
            2,
            0,
            {"shots": 9, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 24},
            {"shots": 2, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 8},
            [],
        ),
        detail(
            "2026-04-18T08:30:00Z",
            78,
            2,
            0,
            {"shots": 9, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 25},
            {"shots": 3, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 9},
            [],
        ),
    ]
    metrics = build_rolling_metrics(history)
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
    hydrated = populate_input_with_metrics(base, metrics)
    assert hydrated.shots_last_10 == 2
    assert hydrated.corners_last_10 == 1
    assert hydrated.data_confidence_flag is True
    assert "shots_last_10" in hydrated.source_fields_present
