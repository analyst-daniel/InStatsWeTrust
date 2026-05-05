from datetime import datetime, timezone

import pandas as pd

from app.js_dashboard.server import (
    build_diagnostic_funnel,
    build_proof_debug_rows,
    summarize_capital_usage,
    summarize_process_focus,
    summarize_yesterday_capital_usage,
    summarize_missing_detail_history_diagnostics,
    summarize_missing_fixture_diagnostics,
    summarize_no_play_rejections,
    summarize_trades,
    summarize_trade_attribution,
    update_capital_high_watermark,
)
from app.live_state.cache import LiveStateCache
from app.live_state.football_research import FootballResearchStore
from app.live_state.matcher import LiveStateMatcher
from app.normalize.models import LiveState, NormalizedMarket
from app.strategy.goal_totals_under_reporting import build_goal_totals_under_debug_rows
from app.strategy.goal_totals_under_runtime import GoalTotalsUnderRuntime
from app.strategy.proof_of_winning_runtime import ProofOfWinningRuntime


def fixture_row(elapsed: int, home_goals: int = 2, away_goals: int = 0) -> dict:
    return {
        "fixture": {
            "id": 12345,
            "date": "2026-04-18T10:00:00+00:00",
            "status": {"short": "2H", "elapsed": elapsed},
        },
        "teams": {"home": {"name": "Cerezo Osaka"}, "away": {"name": "Kyoto Sanga FC"}},
        "goals": {"home": home_goals, "away": away_goals},
        "league": {"name": "J1 League", "sport": "Football"},
    }


def stats_payload(values: dict) -> list[dict]:
    return [
        {"type": "Total Shots", "value": values.get("shots", 0)},
        {"type": "Shots on Goal", "value": values.get("shots_on_target", 0)},
        {"type": "Corner Kicks", "value": values.get("corners", 0)},
        {"type": "Dangerous Attacks", "value": values.get("dangerous_attacks", 0)},
        {"type": "Red Cards", "value": values.get("red_cards", 0)},
    ]


def write_detail(store: FootballResearchStore, elapsed: int, away_shots: int, away_da: int, away_corners: int = 0) -> None:
    store.write_fixture_detail(
        "12345",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC",
        fixture_payload=fixture_row(elapsed),
        statistics=[
            {"team": {"name": "Cerezo Osaka"}, "statistics": stats_payload({"shots": 10, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 26})},
            {"team": {"name": "Kyoto Sanga FC"}, "statistics": stats_payload({"shots": away_shots, "shots_on_target": 0, "corners": away_corners, "dangerous_attacks": away_da})},
        ],
        events=[
            {"time": {"elapsed": 31, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
            {"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
        ],
    )


def test_build_proof_debug_rows_returns_enter_and_reason(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    write_detail(store, 65, 1, 5)
    write_detail(store, 70, 2, 7)
    write_detail(store, 75, 3, 8)
    write_detail(store, 76, 3, 8)
    write_detail(store, 78, 3, 8)

    cache = LiveStateCache(tmp_path / "live_state.json")
    state = LiveState(
        slug="j1100-cer-kyo-2026-04-18-more-markets",
        sport="soccer",
        live=True,
        ended=False,
        score="2-0",
        period="2H",
        elapsed=78.0,
        last_update=datetime.now(timezone.utc),
        raw=fixture_row(78),
    )
    cache._states[state.slug] = state
    cache.save()
    matcher = LiveStateMatcher(cache, max_age_seconds=120)
    runtime = ProofOfWinningRuntime({"proof_of_winning": {"enabled": True, "history_limit": 16}}, store)
    market = NormalizedMarket(
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id="1674823",
        market_slug="j1100-cer-kyo-2026-04-18-cerezo-win",
        question="Will Cerezo Osaka win on 2026-04-18?",
        sport="soccer",
        category="sports",
        teams=["Cerezo Osaka", "Kyoto Sanga FC"],
        active=True,
        closed=False,
        token_ids=["yes-token", "no-token"],
        yes_token_id="yes-token",
        no_token_id="no-token",
        outcomes=["Yes", "No"],
        best_bid_yes=0.96,
        best_ask_yes=0.97,
        best_bid_no=0.03,
        best_ask_no=0.04,
        timestamp_utc=datetime.now(timezone.utc),
    )
    latest = pd.DataFrame(
        [
            {
                "timestamp_utc": "2026-04-18T10:00:00Z",
                "event_id": "296790",
                "event_slug": "j1100-cer-kyo-2026-04-18-more-markets",
                "event_title": "Cerezo Osaka vs Kyoto Sanga FC - More Markets",
                "market_id": "1674823",
                "market_slug": "j1100-cer-kyo-2026-04-18-cerezo-win",
                "question": "Will Cerezo Osaka win on 2026-04-18?",
                "token_id": "yes-token",
                "side": "Yes",
                "price": 0.97,
                "bid": 0.96,
                "ask": 0.97,
                "spread": 0.01,
                "liquidity": 1000.0,
                "last_trade_price": 0.97,
                "sport": "soccer",
                "live": 1,
                "ended": 0,
                "score": "2-0",
                "period": "2H",
                "elapsed": 78,
                "reason": "trade_eligible_price_held",
            }
        ]
    )
    rows = build_proof_debug_rows(latest, {(market.event_id, market.market_id): market}, matcher, runtime)
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["final_decision"] == "ENTER"
    assert row["rejection_reason"] == ""
    assert row["goal_difference"] == 2
    assert row["shots_last_10"] == 2


def test_build_goal_totals_under_debug_rows_returns_enter_and_buffer(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    store.write_fixture_detail(
        "12345",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC",
        fixture_payload=fixture_row(58, 1, 0),
        statistics=[
            {
                "team": {"name": "Cerezo Osaka"},
                "statistics": [
                    {"type": "Total Shots", "value": 1},
                    {"type": "Shots on Goal", "value": 1},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 6},
                    {"type": "Attacks", "value": 12},
                    {"type": "Red Cards", "value": 0},
                ],
            },
            {
                "team": {"name": "Kyoto Sanga FC"},
                "statistics": [
                    {"type": "Total Shots", "value": 1},
                    {"type": "Shots on Goal", "value": 0},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 2},
                    {"type": "Attacks", "value": 6},
                    {"type": "Red Cards", "value": 0},
                ],
            },
        ],
        events=[{"time": {"elapsed": 12, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}}],
    )
    store.write_fixture_detail(
        "12345",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC",
        fixture_payload=fixture_row(63, 1, 0),
        statistics=[
            {
                "team": {"name": "Cerezo Osaka"},
                "statistics": [
                    {"type": "Total Shots", "value": 2},
                    {"type": "Shots on Goal", "value": 1},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 8},
                    {"type": "Attacks", "value": 14},
                    {"type": "Red Cards", "value": 0},
                ],
            },
            {
                "team": {"name": "Kyoto Sanga FC"},
                "statistics": [
                    {"type": "Total Shots", "value": 1},
                    {"type": "Shots on Goal", "value": 0},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 3},
                    {"type": "Attacks", "value": 8},
                    {"type": "Red Cards", "value": 0},
                ],
            },
        ],
        events=[{"time": {"elapsed": 12, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}}],
    )
    store.write_fixture_detail(
        "12345",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC",
        fixture_payload=fixture_row(68, 1, 0),
        statistics=[
            {
                "team": {"name": "Cerezo Osaka"},
                "statistics": [
                    {"type": "Total Shots", "value": 3},
                    {"type": "Shots on Goal", "value": 1},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 10},
                    {"type": "Attacks", "value": 18},
                    {"type": "Red Cards", "value": 0},
                ],
            },
            {
                "team": {"name": "Kyoto Sanga FC"},
                "statistics": [
                    {"type": "Total Shots", "value": 1},
                    {"type": "Shots on Goal", "value": 0},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 4},
                    {"type": "Attacks", "value": 10},
                    {"type": "Red Cards", "value": 0},
                ],
            },
        ],
        events=[{"time": {"elapsed": 12, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}}],
    )
    store.write_fixture_detail(
        "12345",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC",
        fixture_payload=fixture_row(73, 1, 0),
        statistics=[
            {
                "team": {"name": "Cerezo Osaka"},
                "statistics": [
                    {"type": "Total Shots", "value": 4},
                    {"type": "Shots on Goal", "value": 1},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 12},
                    {"type": "Attacks", "value": 20},
                    {"type": "Red Cards", "value": 0},
                ],
            },
            {
                "team": {"name": "Kyoto Sanga FC"},
                "statistics": [
                    {"type": "Total Shots", "value": 1},
                    {"type": "Shots on Goal", "value": 0},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 5},
                    {"type": "Attacks", "value": 12},
                    {"type": "Red Cards", "value": 0},
                ],
            },
        ],
        events=[{"time": {"elapsed": 12, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}}],
    )
    store.write_fixture_detail(
        "12345",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC",
        fixture_payload=fixture_row(78, 1, 0),
        statistics=[
            {
                "team": {"name": "Cerezo Osaka"},
                "statistics": [
                    {"type": "Total Shots", "value": 5},
                    {"type": "Shots on Goal", "value": 1},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 14},
                    {"type": "Attacks", "value": 24},
                    {"type": "Red Cards", "value": 0},
                ],
            },
            {
                "team": {"name": "Kyoto Sanga FC"},
                "statistics": [
                    {"type": "Total Shots", "value": 1},
                    {"type": "Shots on Goal", "value": 0},
                    {"type": "Corner Kicks", "value": 0},
                    {"type": "Dangerous Attacks", "value": 6},
                    {"type": "Attacks", "value": 14},
                    {"type": "Red Cards", "value": 0},
                ],
            },
        ],
        events=[{"time": {"elapsed": 12, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}}],
    )

    cache = LiveStateCache(tmp_path / "live_state.json")
    state = LiveState(
        slug="j1100-cer-kyo-2026-04-18-more-markets",
        sport="soccer",
        live=True,
        ended=False,
        score="1-0",
        period="2H",
        elapsed=78.0,
        last_update=datetime.now(timezone.utc),
        raw=fixture_row(78, 1, 0),
    )
    cache._states[state.slug] = state
    cache.save()
    matcher = LiveStateMatcher(cache, max_age_seconds=120)
    runtime = GoalTotalsUnderRuntime({"goal_totals_under": {"enabled": True, "history_limit": 16}}, store)
    market = NormalizedMarket(
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id="1674823",
        market_slug="j1100-cer-kyo-2026-04-18-ou-3pt5",
        question="Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5",
        sport="soccer",
        category="sports",
        teams=["Cerezo Osaka", "Kyoto Sanga FC"],
        active=True,
        closed=False,
        token_ids=["over-token", "under-token"],
        yes_token_id="over-token",
        no_token_id="under-token",
        outcomes=["Over", "Under"],
        best_bid_yes=0.02,
        best_ask_yes=0.03,
        best_bid_no=0.96,
        best_ask_no=0.97,
        timestamp_utc=datetime.now(timezone.utc),
    )
    latest = pd.DataFrame(
        [
            {
                "timestamp_utc": "2026-04-18T10:00:00Z",
                "event_id": "296790",
                "event_slug": "j1100-cer-kyo-2026-04-18-more-markets",
                "event_title": "Cerezo Osaka vs Kyoto Sanga FC - More Markets",
                "market_id": "1674823",
                "market_slug": "j1100-cer-kyo-2026-04-18-ou-3pt5",
                "question": "Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5",
                "token_id": "under-token",
                "side": "Under",
                "price": 0.97,
                "bid": 0.96,
                "ask": 0.97,
                "spread": 0.01,
                "liquidity": 1000.0,
                "last_trade_price": 0.97,
                "sport": "soccer",
                "live": 1,
                "ended": 0,
                "score": "1-0",
                "period": "2H",
                "elapsed": 78,
                "market_type": "total",
                "total_line": 3.5,
                "total_selected_side_type": "under",
                "total_goals": 1,
                "total_goal_buffer": 2.5,
                "reason": "trade_eligible_price_held",
            }
        ]
    )
    rows = build_goal_totals_under_debug_rows(
        latest,
        {(market.event_id, market.market_id): market},
        matcher,
        runtime,
        parse_dt=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        to_float=float,
        to_optional_float=lambda value: None if value in ("", None) else float(value),
        to_bool=bool,
    )
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["final_decision"] == "ENTER"
    assert row["rejection_reason"] == ""
    assert row["goal_buffer"] == 2.5
    assert row["total_line"] == 3.5
    assert row["total_goals"] == 1


def test_summarize_no_play_rejections_groups_reason_counts() -> None:
    df = pd.DataFrame(
        [
            {"event_id": "e1", "market_id": "m1", "reason": "snapshot_only_no_play_draw_market"},
            {"event_id": "e1", "market_id": "m2", "reason": "snapshot_only_no_play_draw_market"},
            {"event_id": "e2", "market_id": "m3", "reason": "snapshot_only_no_play_btts"},
        ]
    )
    summary = summarize_no_play_rejections(df)
    assert len(summary) == 2
    first = summary.iloc[0]
    assert first["group"] == "snapshot_only_no_play_draw_market"
    assert first["rows"] == 2
    assert first["events"] == 1
    assert first["markets"] == 2


def test_summarize_trades_separates_resolved_voided_and_stale() -> None:
    trades = pd.DataFrame(
        [
            {"status": "resolved", "stake_usd": 10.0, "pnl_usd": 1.0},
            {"status": "resolved", "stake_usd": 11.0, "pnl_usd": -2.0},
            {"status": "resolved", "stake_usd": 12.0, "pnl_usd": 0.0},
            {"status": "open", "stake_usd": 13.0, "pnl_usd": ""},
            {"status": "voided_bad_feed", "stake_usd": 14.0, "pnl_usd": 0.0},
            {"status": "stale_closed", "stake_usd": 15.0, "pnl_usd": ""},
        ]
    )

    summary = summarize_trades(trades)

    assert summary["total_trades"] == 4
    assert summary["open_trades"] == 1
    assert summary["resolved_trades"] == 3
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["pushes"] == 1
    assert summary["voided_bad_feed"] == 1
    assert summary["stale_closed"] == 1
    assert summary["stake_usd"] == 33.0
    assert summary["pnl_usd"] == -1.0


def test_build_diagnostic_funnel_counts_rows() -> None:
    summary, rows = build_diagnostic_funnel(
        events=[{"id": "1"}, {"id": "2"}],
        matches=pd.DataFrame([{"event_id": "1"}, {"event_id": "2"}]),
        raw_snapshots=pd.DataFrame([{"event_id": "1"}, {"event_id": "2"}, {"event_id": "2"}]),
        snapshots=pd.DataFrame([{"event_id": "1"}]),
        pregame=pd.DataFrame([{"event_id": "1"}]),
        started=pd.DataFrame([{"event_id": "1"}]),
        live75=pd.DataFrame(),
        no_play_latest=pd.DataFrame([{"event_id": "1"}]),
        proof_debug=pd.DataFrame([{"final_decision": "ENTER"}, {"final_decision": "NO ENTER"}]),
        spread_debug=pd.DataFrame([{"final_decision": "NO ENTER"}]),
        goal_totals_under_debug=pd.DataFrame([{"final_decision": "ENTER"}]),
    )

    assert summary["events_seen"] == 2
    assert summary["soccer_events"] == 2
    assert summary["pregame_matches"] == 1
    assert summary["started_matches"] == 1
    assert summary["raw_price_window_rows"] == 3
    assert summary["fresh_price_window_rows"] == 1
    assert summary["no_play_rejected_rows"] == 1
    assert summary["proof_enter"] == 1
    assert summary["under_enter"] == 1
    assert len(rows) >= 10


def test_summarize_missing_fixture_diagnostics_groups_by_reason_event_and_question() -> None:
    proof = pd.DataFrame(
        [
            {
                "rejection_reason": "proof_of_winning_missing_fixture_id",
                "event_title": "Match A",
                "league": "League 1",
                "question": "Will Team A win?",
            }
        ]
    )
    spread = pd.DataFrame(
        [
            {
                "rejection_reason": "spread_confirmation_missing_fixture_id",
                "event_title": "Match B",
                "league": "League 2",
                "question": "Spread: Team B (-1.5)",
            },
            {
                "rejection_reason": "spread_confirmation_missing_fixture_id",
                "event_title": "Match B",
                "league": "League 2",
                "question": "Spread: Team B (-1.5)",
            },
        ]
    )
    under = pd.DataFrame(
        [
            {
                "rejection_reason": "goal_totals_under_low_data_confidence",
                "event_title": "Match C",
                "league": "League 3",
                "question": "Team C: O/U 3.5",
            }
        ]
    )

    summary, rows = summarize_missing_fixture_diagnostics(proof, spread, under)

    assert summary == {"rows": 3, "events": 2, "questions": 2, "leagues": 2}
    assert len(rows) == 2
    assert rows.iloc[0]["reason"] == "spread_confirmation_missing_fixture_id"
    assert rows.iloc[0]["rows"] == 2


def test_summarize_missing_detail_history_diagnostics_groups_by_reason_event_and_question() -> None:
    proof = pd.DataFrame(
        [
            {
                "rejection_reason": "proof_of_winning_missing_detail_history",
                "event_title": "Match A",
                "league": "League 1",
                "question": "Will Team A win?",
            }
        ]
    )
    spread = pd.DataFrame(
        [
            {
                "rejection_reason": "spread_confirmation_missing_detail_history",
                "event_title": "Match B",
                "league": "League 2",
                "question": "Spread: Team B (-1.5)",
            },
            {
                "rejection_reason": "spread_confirmation_missing_detail_history",
                "event_title": "Match B",
                "league": "League 2",
                "question": "Spread: Team B (-1.5)",
            },
        ]
    )
    under = pd.DataFrame(
        [
            {
                "rejection_reason": "goal_totals_under_low_data_confidence",
                "event_title": "Match C",
                "league": "League 3",
                "question": "Team C: O/U 3.5",
            }
        ]
    )

    summary, rows = summarize_missing_detail_history_diagnostics(proof, spread, under)

    assert summary == {"rows": 3, "events": 2, "questions": 2, "leagues": 2}
    assert len(rows) == 2
    assert rows.iloc[0]["reason"] == "spread_confirmation_missing_detail_history"
    assert rows.iloc[0]["rows"] == 2


def test_summarize_trade_attribution_groups_resolved_trades() -> None:
    trades = pd.DataFrame(
        [
            {
                "trade_id": "t1",
                "status": "resolved",
                "entry_reason": "proof_of_winning_enter",
                "question": "Will Cerezo Osaka win on 2026-04-18?",
                "side": "Yes",
                "event_slug": "j1100-cer-kyo-2026-04-18-more-markets",
                "elapsed": 78,
                "entry_price": 0.97,
                "score": "2-0",
                "pnl_usd": 0.3,
            },
            {
                "trade_id": "t2",
                "status": "resolved",
                "entry_reason": "goal_totals_under_enter",
                "question": "Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5",
                "side": "Under",
                "event_slug": "j1100-cer-kyo-2026-04-18-more-markets",
                "elapsed": 81,
                "entry_price": 0.96,
                "score": "1-0",
                "pnl_usd": -10.0,
            },
        ]
    )
    summary, by_strategy, by_subtype, by_league, by_entry_bucket, by_price_bucket, by_goal_buffer = summarize_trade_attribution(trades)
    assert summary["resolved"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert "proof" in set(by_strategy["group"])
    assert "under" in set(by_strategy["group"])
    assert "J1 League" in set(by_league["group"])
    assert "75-79" in set(by_entry_bucket["group"])
    assert "0.97-0.979" in set(by_price_bucket["group"])
    assert "2+" in set(by_goal_buffer["group"])


def test_summarize_trade_attribution_empty_returns_all_tables() -> None:
    result = summarize_trade_attribution(pd.DataFrame())

    assert len(result) == 7
    summary, *tables = result
    assert summary == {"total": 0, "resolved": 0, "wins": 0, "losses": 0, "pnl_usd": 0.0, "win_rate": ""}
    assert all(table.empty for table in tables)


def test_summarize_process_focus_returns_only_active_processes_above_start() -> None:
    processes = pd.DataFrame(
        [
            {"process_id": "p1", "status": "ready", "current_balance": 10.0, "step_count": 1, "open_trade_id": "", "last_result": ""},
            {"process_id": "p2", "status": "ready", "current_balance": 12.3, "step_count": 2, "open_trade_id": "", "last_result": "resolved"},
            {"process_id": "p3", "status": "in_trade", "current_balance": 11.1, "step_count": 3, "open_trade_id": "t3", "last_result": "resolved"},
            {"process_id": "p4", "status": "completed", "current_balance": 21.0, "step_count": 4, "open_trade_id": "", "last_result": "resolved"},
        ]
    )
    summary, rows = summarize_process_focus(processes, start_balance=10.0)
    assert summary["active_processes"] == 3
    assert summary["active_above_start"] == 2
    assert summary["ready_processes"] == 2
    assert summary["in_trade_processes"] == 1
    assert summary["balance_above_start"] == 23.4
    assert [row["process_id"] for row in rows] == ["p2", "p3"]


def test_summarize_capital_usage_counts_runs_continuations_and_peak() -> None:
    processes = pd.DataFrame(
        [
            {
                "process_id": "p1",
                "created_at": "2026-05-03T10:00:00+00:00",
                "closed_at": "2026-05-03T12:00:00+00:00",
                "step_count": 3,
            },
            {
                "process_id": "p2",
                "created_at": "2026-05-03T11:00:00+00:00",
                "closed_at": "2026-05-03T13:00:00+00:00",
                "step_count": 2,
            },
            {
                "process_id": "p3",
                "created_at": "2026-05-03T14:00:00+00:00",
                "closed_at": "",
                "step_count": 1,
            },
        ]
    )

    summary = summarize_capital_usage(processes, start_balance=10.0)

    assert summary["capital_runs"] == 3
    assert summary["continuations"] == 3
    assert summary["max_parallel_runs"] == 2
    assert summary["min_start_capital"] == 20.0


def test_summarize_yesterday_capital_usage_counts_locked_trade_stake() -> None:
    now_berlin = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Europe/Berlin"))
    yday = now_berlin.date() - pd.Timedelta(days=1)
    rows = pd.DataFrame(
        [
            {
                "trade_id": "t1",
                "process_id": "p1",
                "entry_timestamp": datetime(yday.year, yday.month, yday.day, 10, 0, tzinfo=timezone.utc).isoformat(),
                "resolved_at": datetime(yday.year, yday.month, yday.day, 12, 0, tzinfo=timezone.utc).isoformat(),
                "stake_usd": 10.0,
            },
            {
                "trade_id": "t2",
                "process_id": "p1",
                "entry_timestamp": datetime(yday.year, yday.month, yday.day, 11, 0, tzinfo=timezone.utc).isoformat(),
                "resolved_at": datetime(yday.year, yday.month, yday.day, 13, 0, tzinfo=timezone.utc).isoformat(),
                "stake_usd": 12.5,
            },
            {
                "trade_id": "t3",
                "process_id": "p2",
                "entry_timestamp": datetime(yday.year, yday.month, yday.day, 11, 30, tzinfo=timezone.utc).isoformat(),
                "resolved_at": datetime(yday.year, yday.month, yday.day, 11, 45, tzinfo=timezone.utc).isoformat(),
                "stake_usd": 20.0,
            },
        ]
    )

    summary = summarize_yesterday_capital_usage(rows, start_balance=10.0)

    assert summary["yday_trades"] == 3
    assert summary["yday_capital_runs"] == 2
    assert summary["yday_peak_open_trades"] == 3
    assert summary["yday_peak_stake_locked"] == 42.5
    assert summary["yday_min_capital"] == 42.5


def test_update_capital_high_watermark_only_writes_when_record_is_beaten(tmp_path) -> None:
    path = tmp_path / "capital_high_watermark.json"

    first = update_capital_high_watermark(
        path,
        {
            "yday_date": "2026-05-03",
            "yday_min_capital": 100.0,
            "yday_peak_open_trades": 10,
            "yday_peak_stake_locked": 100.0,
        },
    )
    second = update_capital_high_watermark(
        path,
        {
            "yday_date": "2026-05-04",
            "yday_min_capital": 90.0,
            "yday_peak_open_trades": 9,
            "yday_peak_stake_locked": 90.0,
        },
    )
    third = update_capital_high_watermark(
        path,
        {
            "yday_date": "2026-05-05",
            "yday_min_capital": 120.0,
            "yday_peak_open_trades": 12,
            "yday_peak_stake_locked": 120.0,
        },
    )

    assert first["capital_record"] == 100.0
    assert second["capital_record"] == 100.0
    assert second["capital_record_date"] == "2026-05-03"
    assert third["capital_record"] == 120.0
    assert third["capital_record_date"] == "2026-05-05"
