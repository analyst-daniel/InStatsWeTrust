from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.discovery.gamma_client import GammaClient
from app.discovery.cache import DiscoveryCache
from app.discovery.expand import expand_events_to_all_markets
from app.discovery.related import fetch_related_live_events
from app.live_state.cache import LiveStateCache
from app.live_state.football_research import FootballResearchStore
from app.live_state.matcher import LiveStateMatcher
from app.normalize.models import PaperTrade
from app.normalize.normalizer import normalize_events
from app.paper_trader.trader import PaperTrader
from app.risk.limits import RiskManager
from app.storage.store import Store
from app.storage.trades import load_trades
from app.strategy.date_guard import market_date_is_current_or_unknown
from app.strategy.hold_confirm import HoldConfirmation
from app.strategy.engine import StrategyEngine
from app.strategy.goal_totals_under_runtime import GoalTotalsUnderRuntime
from app.strategy.proof_of_winning_runtime import ProofOfWinningRuntime
from app.strategy.spread_confirmation_runtime import SpreadConfirmationRuntime
from app.utils.config import load_settings, resolve_path
from app.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    logger = setup_logging(resolve_path(settings["storage"]["log_dir"]), name="scanner")
    store = Store(
        resolve_path(settings["storage"]["sqlite_path"]),
        resolve_path(settings["storage"]["snapshot_csv"]),
        resolve_path(settings["storage"]["trade_csv"]),
    )
    client = GammaClient(settings, resolve_path(settings["storage"]["raw_dir"]))
    discovery_cache = DiscoveryCache(resolve_path(settings["storage"]["discovery_cache_json"]))
    live_cache = LiveStateCache(resolve_path(settings["storage"]["live_state_json"]))
    trade_live_state_max_age = int(
        settings.get("validation", {}).get(
            "trade_live_state_max_age_seconds",
            settings.get("dashboard", {}).get("live_state_max_age_seconds", 90),
        )
    )
    matcher = LiveStateMatcher(live_cache, max_age_seconds=trade_live_state_max_age)
    strategy = StrategyEngine(settings)
    proof_runtime = ProofOfWinningRuntime(
        settings,
        FootballResearchStore(
            manifest_path=resolve_path(settings["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(settings["storage"]["raw_dir"]),
        ),
    )
    spread_runtime = SpreadConfirmationRuntime(
        settings,
        FootballResearchStore(
            manifest_path=resolve_path(settings["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(settings["storage"]["raw_dir"]),
        ),
    )
    goal_totals_under_runtime = GoalTotalsUnderRuntime(
        settings,
        FootballResearchStore(
            manifest_path=resolve_path(settings["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(settings["storage"]["raw_dir"]),
        ),
    )
    trader = PaperTrader(settings, RiskManager(settings))
    hold = HoldConfirmation(
        resolve_path(settings["storage"]["hold_state_json"]),
        float(settings["strategy"].get("min_price_hold_seconds", 5)),
    )
    interval = int(settings["scanner"].get("interval_seconds", 5))
    full_every = max(1, int(settings["scanner"].get("full_discovery_every_cycles", 12)))
    snapshot_only_live = bool(settings["strategy"].get("snapshot_only_live", True))
    require_fresh_live_state = bool(settings.get("validation", {}).get("require_fresh_live_state_for_candidates", True))
    target_sport = str(settings["strategy"].get("sport", "soccer")).lower()
    cycle = 0
    print(f"Scanner running every {interval}s. Waiting for each API cycle to finish...", flush=True)

    while True:
        started = datetime.utcnow().isoformat()
        try:
            cycle += 1
            live_cache.load()
            cached_events = discovery_cache.load()
            if not cached_events or cycle % full_every == 1:
                events = client.fetch_all_events()
                if settings["discovery"].get("related_more_markets_enabled", True):
                    related = fetch_related_live_events(
                        client,
                        live_cache,
                        limit=int(settings["discovery"].get("related_search_limit_per_cycle", 8)),
                    )
                    if related:
                        known = {str(event.get("id") or event.get("slug") or "") for event in events}
                        for event in related:
                            key = str(event.get("id") or event.get("slug") or "")
                            if key not in known:
                                events.append(event)
                                known.add(key)
                if settings["discovery"].get("expand_event_details_enabled", True):
                    events = expand_events_to_all_markets(
                        client,
                        events,
                        live_cache,
                        limit=int(settings["discovery"].get("expand_event_detail_limit", 25)),
                        pregame_window_minutes=int(settings["discovery"].get("pregame_window_minutes", 360)),
                    )
                discovery_cache.save(events)
                discovery_mode = "full"
            else:
                events = cached_events
                discovery_mode = "cache"
            markets = normalize_events(events)
            open_and_history = load_trades(resolve_path(settings["storage"]["trade_csv"]))
            observations = []
            entries = []
            latest_by_token = {}
            eligible = 0
            for market in markets:
                if market.sport.lower() != target_sport:
                    continue
                if not market_date_is_current_or_unknown(market):
                    continue
                live_state = matcher.match(market)
                if require_fresh_live_state and live_state is None:
                    continue
                for decision in strategy.evaluate_market(market, live_state):
                    if snapshot_only_live and not (live_state and live_state.live and not live_state.ended):
                        continue
                    if decision.eligible_for_trade:
                        spread = spread_runtime.evaluate(market, decision.observation, live_state)
                        if spread.applies:
                            decision.observation.reason = spread.reason
                            decision = type(decision)(
                                observation=decision.observation,
                                eligible_for_trade=spread.enter,
                                reason=spread.reason,
                            )
                    if decision.eligible_for_trade:
                        proof = proof_runtime.evaluate(market, decision.observation, live_state)
                        if proof.applies:
                            decision.observation.reason = proof.reason
                            decision = type(decision)(
                                observation=decision.observation,
                                eligible_for_trade=proof.enter,
                                reason=proof.reason,
                            )
                    if decision.eligible_for_trade:
                        totals_under = goal_totals_under_runtime.evaluate(market, decision.observation, live_state)
                        if totals_under.applies:
                            decision.observation.reason = totals_under.reason
                            decision = type(decision)(
                                observation=decision.observation,
                                eligible_for_trade=totals_under.enter,
                                reason=totals_under.reason,
                            )
                    observations.append(decision.observation)
                    latest_by_token[decision.observation.token_id] = decision.observation.price
                    if decision.eligible_for_trade:
                        strategy_reason = decision.observation.reason or decision.reason or "trade_eligible"
                        confirmed, hold_reason = hold.check(decision.observation)
                        decision.observation.reason = f"{strategy_reason}_{hold_reason}"
                        if not confirmed:
                            continue
                        eligible += 1
                        entry = trader.maybe_enter(decision.observation, open_and_history + entries)
                        if entry:
                            entries.append(entry)
            hold.save()
            updates = trader.update_open_trades(open_and_history + entries, latest_by_token)
            store.append_snapshots(observations)
            store.upsert_trades(entries + updates)
            logger.info(
                "scan started=%s mode=%s events=%s markets=%s snapshots=%s eligible=%s entries=%s updates=%s",
                started,
                discovery_mode,
                len(events),
                len(markets),
                len(observations),
                eligible,
                len(entries),
                len(updates),
            )
            print(f"{datetime.utcnow().isoformat()} mode={discovery_mode} events={len(events)} markets={len(markets)} snapshots={len(observations)} eligible={eligible} entries={len(entries)}", flush=True)
        except Exception:
            logger.exception("scanner cycle failed")
        if args.once:
            break
        time.sleep(interval)
if __name__ == "__main__":
    main()
