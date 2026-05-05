from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.normalize.normalizer import market_type
from app.strategy.goal_totals_under import build_goal_totals_under_input
from app.strategy.spread_confirmation import SpreadSideType, parse_spread_market, selected_team_margin


@dataclass(frozen=True)
class CandidateDecision:
    observation: MarketObservation
    eligible_for_trade: bool
    reason: str


class StrategyEngine:
    def __init__(self, settings: dict) -> None:
        strategy = settings["strategy"]
        self.sport = str(strategy.get("sport", "soccer")).lower()
        self.min_elapsed = float(strategy.get("min_elapsed", 75))
        self.max_elapsed = float(strategy.get("max_elapsed", 89))
        self.min_price = float(strategy.get("min_price", 0.60))
        self.max_price = float(strategy.get("max_price", 1.0))
        self.require_live_state = bool(strategy.get("require_live_state", True))
        self.min_liquidity = float(strategy.get("min_liquidity_usd", strategy.get("min_liquidity", 0)))
        self.max_spread = float(strategy.get("max_spread", 1))

    def evaluate_market(self, market: NormalizedMarket, live_state: LiveState | None) -> list[CandidateDecision]:
        rows: list[CandidateDecision] = []
        for token_id, side, bid, ask in self._sides(market):
            if ask is None:
                continue
            parsed_spread = parse_spread_market(market.question, side)
            parsed_total = build_goal_totals_under_input(
                event_id=market.event_id,
                event_slug=market.event_slug,
                event_title=market.event_title,
                market_id=market.market_id,
                market_slug=market.market_slug,
                question=market.question,
                side=side,
                minute=live_state.elapsed if live_state else None,
                score=live_state.score if live_state else "",
                home_team=market.teams[0] if market.teams else "",
                away_team=market.teams[1] if len(market.teams) > 1 else "",
                data_confidence_flag=bool(live_state),
                red_card_flag=False,
            )
            obs = MarketObservation(
                timestamp_utc=datetime.now(timezone.utc),
                event_id=market.event_id,
                event_slug=market.event_slug,
                event_title=market.event_title,
                market_id=market.market_id,
                market_slug=market.market_slug,
                question=market.question,
                token_id=token_id,
                side=side,
                price=ask,
                bid=bid,
                ask=ask,
                spread=max(ask - bid, 0.0) if bid is not None else market.spread,
                liquidity=market.liquidity,
                last_trade_price=market.last_trade_price,
                sport=market.sport,
                live=bool(live_state.live) if live_state else False,
                ended=bool(live_state.ended) if live_state else False,
                score=live_state.score if live_state else "",
                period=live_state.period if live_state else "",
                elapsed=live_state.elapsed if live_state else None,
                market_type=market_type(market.question),
                spread_listed_team=parsed_spread.listed_team,
                spread_listed_line=parsed_spread.line,
                spread_listed_side_type=parsed_spread.side_type.value,
                spread_selected_team=parsed_spread.selected_team,
                spread_selected_line=parsed_spread.selected_line,
                spread_selected_side_type=parsed_spread.selected_side_type.value,
                total_line=parsed_total.total_line,
                total_selected_side_type=parsed_total.selected_side_type.value,
                total_goals=parsed_total.total_goals,
                total_goal_buffer=parsed_total.goal_buffer,
                reason="price_observed",
            )
            eligible, reason = self._eligible(market, obs, live_state)
            obs.reason = reason
            rows.append(CandidateDecision(observation=obs, eligible_for_trade=eligible, reason=reason))
        return rows

    def _eligible(self, market: NormalizedMarket, obs: MarketObservation, live_state: LiveState | None) -> tuple[bool, str]:
        if market.sport.lower() != self.sport:
            return False, "snapshot_only_wrong_sport"
        if market.closed or not market.active:
            return False, "snapshot_only_market_not_active"
        if self.require_live_state and live_state is None:
            return False, "snapshot_only_missing_live_state"
        if live_state is None:
            return False, "snapshot_only_missing_live_state"
        if live_state.ended:
            return False, "snapshot_only_game_ended"
        if not live_state.live:
            return False, "snapshot_only_not_live"
        if live_state.elapsed is None:
            return False, "snapshot_only_missing_elapsed"
        if not (self.min_elapsed <= live_state.elapsed < self.max_elapsed):
            return False, "snapshot_only_elapsed_outside_window"
        if obs.price < self.min_price:
            return False, "snapshot_only_price_below_min"
        if obs.price > self.max_price:
            return False, "snapshot_only_price_above_max"
        if obs.spread is not None and obs.spread > self.max_spread:
            return False, "snapshot_only_spread_too_wide"
        if market.liquidity is not None and market.liquidity < self.min_liquidity:
            return False, "snapshot_only_liquidity_too_low"
        no_play_reason = self._no_play_reason(market, obs, live_state)
        if no_play_reason:
            return False, no_play_reason
        return True, "trade_eligible"

    def _no_play_reason(self, market: NormalizedMarket, obs: MarketObservation, live_state: LiveState) -> str:
        question = str(market.question or "")
        question_lower = question.lower()
        side = str(obs.side or "")
        side_lower = side.lower()
        mtype = market_type(question)
        event_title_lower = str(market.event_title or "").lower()

        if "halftime" in question_lower or "halftime" in event_title_lower:
            return "snapshot_only_no_play_halftime_market"
        if "corner" in question_lower:
            return "snapshot_only_no_play_corners"
        if "anytime goalscorer" in question_lower or "goalscorer" in question_lower:
            return "snapshot_only_no_play_anytime_goalscorer"
        if mtype == "exact_score":
            return "snapshot_only_no_play_exact_score"
        if mtype == "btts":
            return "snapshot_only_no_play_btts"
        if self._is_goal_event_market(question_lower):
            return "snapshot_only_no_play_future_goal_event"

        if mtype == "match":
            if "draw" in question_lower:
                score = self._parse_score(live_state.score)
                if side_lower == "yes":
                    return "snapshot_only_no_play_draw_yes"
                if not score:
                    return "snapshot_only_no_play_draw_no_missing_score"
                goal_difference = abs(score[0] - score[1])
                if goal_difference < 2:
                    return "snapshot_only_no_play_draw_no_margin_too_small"
                return ""
            score = self._parse_score(live_state.score)
            teams = market.teams if len(market.teams) == 2 else self._teams_from_title(market.event_title)
            target_team = self._question_team_name(question)
            if len(teams) == 2 and target_team:
                if not score:
                    return "snapshot_only_no_play_match_winner_missing_score"
                team_state = self._team_match_state(target_team, teams[0], teams[1], score)
                margin = self._team_goal_margin(target_team, teams[0], teams[1], score)
                if side_lower == "yes":
                    if team_state == "trailing":
                        return "snapshot_only_no_play_comeback_required"
                    if team_state == "draw":
                        return "snapshot_only_no_play_match_winner_draw_state"
                    if margin is None or margin < 2:
                        return "snapshot_only_no_play_match_winner_margin_too_small"
                if side_lower == "no":
                    if team_state == "leading":
                        return "snapshot_only_no_play_future_event_required"
                    if team_state == "draw":
                        return "snapshot_only_no_play_match_winner_draw_state"
                    if margin is None or margin > -2:
                        return "snapshot_only_no_play_match_winner_margin_too_small"

        if mtype == "spread":
            score = self._parse_score(live_state.score)
            teams = market.teams if len(market.teams) == 2 else self._teams_from_title(market.event_title)
            if score and len(teams) == 2:
                spread_input = parse_spread_market(question, side)
                if spread_input.valid and spread_input.selected_side_type == SpreadSideType.MINUS:
                    margin = self._selected_team_margin_from_score(spread_input.selected_team, teams[0], teams[1], score)
                    required = self._required_margin_now(spread_input.selected_line)
                    if margin is None or required is None or margin < required:
                        return "snapshot_only_no_play_spread_requires_more_goals"

        return ""

    @staticmethod
    def _is_goal_event_market(question_lower: str) -> bool:
        triggers = [
            "next goal",
            "another goal",
            "any more goals",
            "will there be a goal",
            "to score a goal",
        ]
        return any(trigger in question_lower for trigger in triggers)

    @staticmethod
    def _parse_score(score: str) -> tuple[int, int] | None:
        match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", score or "")
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _teams_from_title(title: str) -> list[str]:
        parts = re.split(r"\s+vs\.?\s+|\s+@\s+", title or "", maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return [parts[0].strip(), parts[1].replace("- More Markets", "").strip()]
        return []

    @staticmethod
    def _question_team_name(question: str) -> str:
        match = re.search(r"Will\s+(.+?)\s+win\b", question or "", flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _normalize_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    def _team_match_state(self, target_team: str, home_team: str, away_team: str, score: tuple[int, int]) -> str:
        home_goals, away_goals = score
        norm_target = self._normalize_name(target_team)
        if norm_target == self._normalize_name(home_team):
            if home_goals > away_goals:
                return "leading"
            if home_goals < away_goals:
                return "trailing"
            return "draw"
        if norm_target == self._normalize_name(away_team):
            if away_goals > home_goals:
                return "leading"
            if away_goals < home_goals:
                return "trailing"
            return "draw"
        return "unknown"

    def _team_goal_margin(self, target_team: str, home_team: str, away_team: str, score: tuple[int, int]) -> int | None:
        home_goals, away_goals = score
        norm_target = self._normalize_name(target_team)
        if norm_target == self._normalize_name(home_team):
            return home_goals - away_goals
        if norm_target == self._normalize_name(away_team):
            return away_goals - home_goals
        return None

    def _selected_team_margin_from_score(
        self,
        selected_team: str,
        home_team: str,
        away_team: str,
        score: tuple[int, int],
    ) -> int | None:
        home_goals, away_goals = score
        norm_selected = self._normalize_name(selected_team)
        if norm_selected == self._normalize_name(home_team):
            return home_goals - away_goals
        if norm_selected == self._normalize_name(away_team):
            return away_goals - home_goals
        return None

    @staticmethod
    def _required_margin_now(selected_line: float | None) -> int | None:
        if selected_line == -1.5:
            return 2
        if selected_line == -2.5:
            return 3
        if selected_line == -3.5:
            return 4
        if selected_line == -4.5:
            return 5
        return None

    @staticmethod
    def _sides(market: NormalizedMarket) -> list[tuple[str, str, float | None, float | None]]:
        side0 = market.outcomes[0] if market.outcomes else "Yes"
        side1 = market.outcomes[1] if len(market.outcomes) > 1 else "No"
        return [
            (market.yes_token_id, side0, market.best_bid_yes, market.best_ask_yes),
            (market.no_token_id, side1, market.best_bid_no, market.best_ask_no),
        ]
