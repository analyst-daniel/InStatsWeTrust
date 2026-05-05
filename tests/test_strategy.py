from __future__ import annotations

from datetime import datetime, timezone

from app.normalize.models import LiveState, NormalizedMarket
from app.strategy.engine import StrategyEngine


def settings() -> dict:
    return {
        "strategy": {
            "sport": "soccer",
            "min_elapsed": 70,
            "max_elapsed": 89,
            "min_price": 0.60,
            "max_price": 0.99,
            "require_live_state": True,
            "min_liquidity_usd": 0,
            "max_spread": 1,
        }
    }


def market() -> NormalizedMarket:
    return NormalizedMarket(
        event_id="e1",
        event_slug="team-a-team-b",
        event_title="Team A FC vs. Team B FC",
        market_id="m1",
        market_slug="m1",
        question="Will Team B FC win?",
        sport="soccer",
        active=True,
        closed=False,
        token_ids=["yes", "no"],
        yes_token_id="yes",
        no_token_id="no",
        outcomes=["Yes", "No"],
        best_bid_yes=0.02,
        best_ask_yes=0.03,
        best_bid_no=0.97,
        best_ask_no=0.98,
        timestamp_utc=datetime.now(timezone.utc),
    )


def live(elapsed: float) -> LiveState:
    return LiveState(slug="team-a-team-b", live=True, ended=False, period="2H", elapsed=elapsed, last_update=datetime.now(timezone.utc))


def test_strategy_enters_only_inside_elapsed_window() -> None:
    engine = StrategyEngine(settings())
    early = engine.evaluate_market(market(), live(70.2).model_copy(update={"score": "2-0"}))
    assert any(d.eligible_for_trade for d in early)
    decisions = engine.evaluate_market(market(), live(75.2).model_copy(update={"score": "2-0"}))
    assert any(d.eligible_for_trade for d in decisions)
    late = engine.evaluate_market(market(), live(89.0).model_copy(update={"score": "2-0"}))
    assert not any(d.eligible_for_trade for d in late)


def test_strategy_snapshot_only_without_live_state() -> None:
    engine = StrategyEngine(settings())
    decisions = engine.evaluate_market(market(), None)
    assert decisions
    assert not decisions[0].eligible_for_trade
    assert decisions[0].reason == "snapshot_only_missing_live_state"


def test_strategy_blocks_any_bet_type_below_min_price() -> None:
    engine = StrategyEngine(settings())
    low_price_market = market().model_copy(
        update={
            "question": "Team A FC vs Team B FC: O/U 2.5",
            "outcomes": ["Over", "Under"],
            "yes_token_id": "over",
            "no_token_id": "under",
            "best_bid_yes": 0.58,
            "best_ask_yes": 0.59,
            "best_bid_no": 0.40,
            "best_ask_no": 0.41,
        }
    )
    decisions = engine.evaluate_market(low_price_market, live(80.0).model_copy(update={"score": "1-0"}))
    low_decision = next(d for d in decisions if d.observation.side == "Over")
    assert not low_decision.eligible_for_trade
    assert low_decision.reason == "snapshot_only_price_below_min"


def test_strategy_blocks_draw_yes_market() -> None:
    engine = StrategyEngine(settings())
    draw_market = market().model_copy(
        update={
            "question": "Will Team A FC vs. Team B FC end in a draw?",
            "outcomes": ["Yes", "No"],
            "yes_token_id": "yes",
            "no_token_id": "no",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.02,
            "best_ask_no": 0.03,
        }
    )
    decisions = engine.evaluate_market(draw_market, live(80.0).model_copy(update={"score": "1-0"}))
    assert decisions
    assert not decisions[0].eligible_for_trade
    assert decisions[0].reason == "snapshot_only_no_play_draw_yes"


def test_strategy_blocks_draw_no_when_margin_below_two() -> None:
    engine = StrategyEngine(settings())
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
    decisions = engine.evaluate_market(draw_market, live(80.0).model_copy(update={"score": "1-0"}))
    no_decision = next(d for d in decisions if d.observation.side == "No")
    assert not no_decision.eligible_for_trade
    assert no_decision.reason == "snapshot_only_no_play_draw_no_margin_too_small"


def test_strategy_allows_draw_no_when_margin_two_plus() -> None:
    engine = StrategyEngine(settings())
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
    decisions = engine.evaluate_market(draw_market, live(85.0).model_copy(update={"score": "3-0"}))
    no_decision = next(d for d in decisions if d.observation.side == "No")
    assert no_decision.eligible_for_trade
    assert no_decision.reason == "trade_eligible"


def test_strategy_blocks_btts_market() -> None:
    engine = StrategyEngine(settings())
    btts_market = market().model_copy(
        update={
            "question": "Both Teams To Score",
            "outcomes": ["Yes", "No"],
            "yes_token_id": "yes",
            "no_token_id": "no",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.96,
            "best_ask_no": 0.97,
        }
    )
    decisions = engine.evaluate_market(btts_market, live(80.0).model_copy(update={"score": "1-0"}))
    assert decisions
    assert not decisions[0].eligible_for_trade
    assert decisions[0].reason == "snapshot_only_no_play_btts"


def test_strategy_blocks_exact_score_market() -> None:
    engine = StrategyEngine(settings())
    exact_market = market().model_copy(
        update={
            "question": "Exact Score: Team A FC 2 - 1 Team B FC",
            "outcomes": ["Yes", "No"],
            "yes_token_id": "yes",
            "no_token_id": "no",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.02,
            "best_ask_no": 0.03,
        }
    )
    decisions = engine.evaluate_market(exact_market, live(80.0).model_copy(update={"score": "2-1"}))
    assert decisions
    assert not decisions[0].eligible_for_trade
    assert decisions[0].reason == "snapshot_only_no_play_exact_score"


def test_strategy_blocks_corners_market() -> None:
    engine = StrategyEngine(settings())
    corners_market = market().model_copy(
        update={
            "question": "Team A FC vs Team B FC: Corners O/U 10.5",
            "outcomes": ["Over", "Under"],
            "yes_token_id": "over",
            "no_token_id": "under",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.96,
            "best_ask_no": 0.97,
        }
    )
    decisions = engine.evaluate_market(corners_market, live(80.0).model_copy(update={"score": "1-0"}))
    assert decisions
    assert not decisions[0].eligible_for_trade
    assert decisions[0].reason == "snapshot_only_no_play_corners"


def test_strategy_blocks_anytime_goalscorer_market() -> None:
    engine = StrategyEngine(settings())
    scorer_market = market().model_copy(
        update={
            "question": "Anytime Goalscorer: Player X",
            "outcomes": ["Yes", "No"],
            "yes_token_id": "yes",
            "no_token_id": "no",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.02,
            "best_ask_no": 0.03,
        }
    )
    decisions = engine.evaluate_market(scorer_market, live(80.0).model_copy(update={"score": "1-0"}))
    assert decisions
    assert not decisions[0].eligible_for_trade
    assert decisions[0].reason == "snapshot_only_no_play_anytime_goalscorer"


def test_strategy_blocks_halftime_result_markets_after_main_window() -> None:
    engine = StrategyEngine(settings())
    halftime_market = market().model_copy(
        update={
            "event_title": "Udinese Calcio vs. Torino FC - Halftime Result",
            "question": "Torino FC leading at halftime?",
            "outcomes": ["Yes", "No"],
            "yes_token_id": "yes",
            "no_token_id": "no",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.02,
            "best_ask_no": 0.03,
        }
    )
    decisions = engine.evaluate_market(halftime_market, live(87.0).model_copy(update={"score": "2-0"}))
    yes_decision = next(d for d in decisions if d.observation.side == "Yes")
    assert not yes_decision.eligible_for_trade
    assert yes_decision.reason == "snapshot_only_no_play_halftime_market"


def test_strategy_blocks_comeback_yes_market() -> None:
    engine = StrategyEngine(settings())
    comeback_market = market().model_copy(
        update={
            "question": "Will Team B FC win?",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.02,
            "best_ask_no": 0.03,
        }
    )
    decisions = engine.evaluate_market(comeback_market, live(80.0).model_copy(update={"score": "1-0"}))
    yes_decision = next(d for d in decisions if d.observation.side == "Yes")
    assert not yes_decision.eligible_for_trade
    assert yes_decision.reason == "snapshot_only_no_play_comeback_required"


def test_strategy_blocks_match_no_when_leader_already_winning() -> None:
    engine = StrategyEngine(settings())
    leader_market = market().model_copy(
        update={
            "question": "Will Team A FC win?",
            "best_bid_yes": 0.02,
            "best_ask_yes": 0.03,
            "best_bid_no": 0.96,
            "best_ask_no": 0.97,
        }
    )
    decisions = engine.evaluate_market(leader_market, live(80.0).model_copy(update={"score": "1-0"}))
    no_decision = next(d for d in decisions if d.observation.side == "No")
    assert not no_decision.eligible_for_trade
    assert no_decision.reason == "snapshot_only_no_play_future_event_required"


def test_strategy_blocks_match_winner_no_when_score_is_draw() -> None:
    engine = StrategyEngine(settings())
    draw_state_market = market().model_copy(
        update={
            "question": "Will Team B FC win?",
            "best_bid_yes": 0.02,
            "best_ask_yes": 0.03,
            "best_bid_no": 0.96,
            "best_ask_no": 0.97,
        }
    )
    decisions = engine.evaluate_market(draw_state_market, live(80.0).model_copy(update={"score": "1-1"}))
    no_decision = next(d for d in decisions if d.observation.side == "No")
    assert not no_decision.eligible_for_trade
    assert no_decision.reason == "snapshot_only_no_play_match_winner_draw_state"


def test_strategy_allows_match_winner_yes_only_with_two_goal_lead() -> None:
    engine = StrategyEngine(settings())
    winner_market = market().model_copy(
        update={
            "question": "Will Team A FC win?",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.02,
            "best_ask_no": 0.03,
        }
    )
    one_goal = engine.evaluate_market(winner_market, live(80.0).model_copy(update={"score": "1-0"}))
    one_goal_yes = next(d for d in one_goal if d.observation.side == "Yes")
    assert not one_goal_yes.eligible_for_trade
    assert one_goal_yes.reason == "snapshot_only_no_play_match_winner_margin_too_small"

    two_goal = engine.evaluate_market(winner_market, live(80.0).model_copy(update={"score": "2-0"}))
    two_goal_yes = next(d for d in two_goal if d.observation.side == "Yes")
    assert two_goal_yes.eligible_for_trade
    assert two_goal_yes.reason == "trade_eligible"


def test_strategy_allows_match_winner_no_only_when_team_trails_by_two() -> None:
    engine = StrategyEngine(settings())
    no_market = market().model_copy(
        update={
            "question": "Will Team B FC win?",
            "best_bid_yes": 0.02,
            "best_ask_yes": 0.03,
            "best_bid_no": 0.96,
            "best_ask_no": 0.97,
        }
    )
    one_goal = engine.evaluate_market(no_market, live(80.0).model_copy(update={"score": "1-0"}))
    one_goal_no = next(d for d in one_goal if d.observation.side == "No")
    assert not one_goal_no.eligible_for_trade
    assert one_goal_no.reason == "snapshot_only_no_play_match_winner_margin_too_small"

    two_goal = engine.evaluate_market(no_market, live(80.0).model_copy(update={"score": "2-0"}))
    two_goal_no = next(d for d in two_goal if d.observation.side == "No")
    assert two_goal_no.eligible_for_trade
    assert two_goal_no.reason == "trade_eligible"


def test_strategy_blocks_minus_spread_that_requires_more_goals() -> None:
    engine = StrategyEngine(settings())
    spread_market = market().model_copy(
        update={
            "question": "Spread: Team A FC (-2.5)",
            "outcomes": ["Team A FC", "Team B FC"],
            "yes_token_id": "home",
            "no_token_id": "away",
            "best_bid_yes": 0.96,
            "best_ask_yes": 0.97,
            "best_bid_no": 0.02,
            "best_ask_no": 0.03,
        }
    )
    decisions = engine.evaluate_market(spread_market, live(80.0).model_copy(update={"score": "1-0"}))
    minus_decision = next(d for d in decisions if d.observation.side == "Team A FC")
    assert not minus_decision.eligible_for_trade
    assert minus_decision.reason == "snapshot_only_no_play_spread_requires_more_goals"
