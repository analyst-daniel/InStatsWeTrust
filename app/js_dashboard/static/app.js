const REFRESH_MS = 10000;
let latestData = {};

const sections = {
  open_trades: [
    "entry_timestamp", "event_title", "question", "bet_label", "side", "entry_price", "stake_usd",
    "entry_minute", "entry_score", "period", "entry_reason", "first_hit_99_at", "first_hit_999_at", "max_favorable_price", "status"
  ],
  resolved_trades: [
    "win", "loss", "resolved_at", "entry_timestamp", "event_title", "question", "bet_label", "side", "entry_price",
    "stake_usd", "entry_minute", "entry_score", "period", "entry_reason", "result", "pnl_usd", "status"
  ],
  live75: [
    "event_title", "league", "score", "period", "confirmed_match_minute", "match_minute", "live_update_age_sec", "market_count",
    "spread_markets", "total_markets", "match_markets", "candidate_count_95_99", "latest_candidate", "league_source", "time_source"
  ],
  started: [
    "event_title", "league", "score", "period", "confirmed_match_minute", "match_minute", "live_update_age_sec", "market_count",
    "spread_markets", "total_markets", "match_markets", "candidate_count_95_99", "latest_candidate", "league_source", "time_source", "live_source"
  ],
  unconfirmed_started: [
    "event_title", "league", "countdown", "estimated_match_minute", "confirmed_match_minute", "minutes_to_start", "start_time_utc", "market_count",
    "spread_markets", "total_markets", "match_markets", "candidate_count_95_99", "latest_candidate", "status_note", "league_source", "time_source", "live_source"
  ],
  unmatched_diagnostic: [
    "event_title", "league", "countdown", "estimated_match_minute", "confirmed_match_minute",
    "minutes_to_start", "start_time_utc", "market_count", "candidate_count_95_99", "latest_candidate", "diagnostic_reason", "league_source", "time_source"
  ],
  pregame: [
    "event_title", "league", "countdown", "start_time_utc", "minutes_to_start", "confirmed_match_minute", "market_count", "spread_markets",
    "total_markets", "match_markets", "candidate_count_95_99", "latest_candidate", "league_source", "time_source"
  ],
  candidates: [
    "timestamp_utc", "event_title", "league", "question", "bet_label", "side", "price", "bid", "ask",
    "spread", "score", "period", "match_minute", "reason"
  ],
  no_play_summary: ["group", "rows", "events", "markets"],
  no_play_rejections: [
    "timestamp_utc", "event_title", "league", "question", "bet_label", "side", "price", "score", "period", "match_minute", "reason"
  ],
  proof_debug: [
    "timestamp_utc", "event_title", "question", "side", "final_decision", "rejection_reason", "minute", "score",
    "goal_difference", "effective_goal_difference", "shots_last_10", "shots_on_target_last_10", "corners_last_10",
    "dangerous_attacks_last_10", "pressure_trend_last_10", "tempo_change_last_10", "goal_in_last_3min",
    "red_card_in_last_10min", "stable_for_2_snapshots", "stable_for_3_snapshots"
  ],
  spread_debug: [
    "timestamp_utc", "event_title", "question", "side", "final_decision", "rejection_reason", "minute", "score",
    "spread_line", "spread_side_type", "selected_team_margin", "goal_difference",
    "leader_shots_last_10", "leader_shots_on_target_last_10", "leader_dangerous_attacks_last_10", "leader_corners_last_10",
    "underdog_shots_last_10", "underdog_shots_on_target_last_10", "underdog_dangerous_attacks_last_10", "underdog_corners_last_10",
    "leader_pressure_trend_last_10", "underdog_pressure_trend_last_10", "shots_trend_last_10", "dangerous_attacks_trend_last_10",
    "tempo_change_last_10", "goal_in_last_3min", "goal_in_last_5min", "red_card_in_last_10min",
    "stable_for_2_snapshots", "stable_for_3_snapshots"
  ],
  goal_totals_under_debug: [
    "timestamp_utc", "event_title", "question", "side", "final_decision", "rejection_reason", "minute", "score",
    "total_line", "total_goals", "goal_buffer", "shots_last_10", "shots_on_target_last_10", "attacks_last_10",
    "dangerous_attacks_last_10", "corners_last_10", "total_shots_both_last_10", "total_dangerous_attacks_both_last_10",
    "total_corners_both_last_10", "pressure_trend_last_10", "shots_trend_last_10", "dangerous_attacks_trend_last_10",
    "tempo_change_last_10", "goal_in_last_3min", "goal_in_last_5min", "red_card_in_last_10min",
    "stable_for_2_snapshots", "stable_for_3_snapshots"
  ],
  goal_totals_under_calibration_line: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  goal_totals_under_calibration_entry_bucket: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  goal_totals_under_calibration_league: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  goal_totals_under_calibration_reason: ["group", "trades", "wins", "losses", "pnl_usd"],
  spread_calibration_line: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  spread_calibration_side_type: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  spread_calibration_entry_bucket: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  spread_calibration_league: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  proof_calibration_market_type: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  proof_calibration_entry_bucket: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
  proof_calibration_league: ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
};

Object.keys(sections).forEach((id) => {
  const target = document.getElementById(id);
  if (target) target.innerHTML = '<div class="empty">loading...</div>';
});

function cellClass(column) {
  return ["event_title", "question", "latest_candidate"].includes(column) ? "wrap" : "";
}

function label(column) {
  return column.replaceAll("_", " ");
}

function renderTable(id, rows, columns) {
  const target = document.getElementById(id);
  if (!rows || rows.length === 0) {
    target.innerHTML = '<div class="empty">empty</div>';
    return;
  }

  const head = columns.map((column) => `<th>${label(column)}</th>`).join("");
  const body = rows.map((row) => {
    const cells = columns.map((column) => {
      const value = row[column] ?? "";
      return `<td class="${cellClass(column)}">${escapeHtml(String(value))}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  target.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function withCountdown(rows) {
  return (rows || []).map((row) => ({
    ...row,
    countdown: countdownText(row.start_time_utc),
    minutes_to_start: minutesToStart(row.start_time_utc, row.minutes_to_start),
  }));
}

function minutesToStart(startTimeUtc, fallback) {
  const start = Date.parse(startTimeUtc || "");
  if (!Number.isFinite(start)) return fallback ?? "";
  return ((start - Date.now()) / 60000).toFixed(1);
}

function countdownText(startTimeUtc) {
  const start = Date.parse(startTimeUtc || "");
  if (!Number.isFinite(start)) return "";
  const diffSeconds = Math.round((start - Date.now()) / 1000);
  const abs = Math.abs(diffSeconds);
  const hours = Math.floor(abs / 3600);
  const minutes = Math.floor((abs % 3600) / 60);
  const seconds = abs % 60;
  const clock = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return diffSeconds >= 0 ? `starts in ${clock}` : `kickoff passed ${clock}`;
}

function enrichTimeRows(rows) {
  return (rows || []).map((row) => {
    const minutes = Number(minutesToStart(row.start_time_utc, row.minutes_to_start));
    const hasConfirmedMinute = row.confirmed_by_sports_api || row.live_source === "sports_api";
    return {
      ...row,
      countdown: countdownText(row.start_time_utc),
      minutes_to_start: Number.isFinite(minutes) ? minutes.toFixed(1) : (row.minutes_to_start ?? ""),
      estimated_match_minute: !hasConfirmedMinute && Number.isFinite(minutes) && minutes < 0
        ? Math.min(Math.max(Math.abs(minutes), 0), 120).toFixed(1)
        : "",
    };
  });
}

function renderStatus(health) {
  const keys = [
    "events", "soccer_matches", "live", "live75",
    "unconfirmed_started", "unmatched", "fresh_candidates", "raw_snapshots", "open_trades", "resolved", "no_play_rejections",
    "pnl_usd", "win_rate"
  ];
  document.getElementById("status").innerHTML = keys.map((key) => (
    `<div class="metric"><span>${label(key)}</span><strong>${escapeHtml(String(health[key] ?? 0))}</strong></div>`
  )).join("");
}

function renderSummary(summary) {
  const target = document.getElementById("trade_summary");
  const keys = [
    "total_trades", "open_trades", "resolved_trades", "wins", "losses", "pushes",
    "stale_closed", "stake_usd", "pnl_usd", "win_rate"
  ];
  target.innerHTML = keys.map((key) => (
    `<div class="metric"><span>${label(key)}</span><strong>${escapeHtml(String(summary[key] ?? ""))}</strong></div>`
  )).join("");
}

function renderProofCalibration(summary) {
  const target = document.getElementById("proof_calibration");
  const keys = ["total", "resolved", "wins", "losses", "pnl_usd", "win_rate"];
  target.innerHTML = keys.map((key) => (
    `<div class="metric"><span>${label(key)}</span><strong>${escapeHtml(String(summary[key] ?? ""))}</strong></div>`
  )).join("");
}

function renderSpreadCalibration(summary) {
  const target = document.getElementById("spread_calibration");
  const keys = ["total", "resolved", "wins", "losses", "pnl_usd", "win_rate"];
  target.innerHTML = keys.map((key) => (
    `<div class="metric"><span>${label(key)}</span><strong>${escapeHtml(String(summary[key] ?? ""))}</strong></div>`
  )).join("");
}

function renderGoalTotalsUnderCalibration(summary) {
  const target = document.getElementById("goal_totals_under_calibration");
  const keys = ["total", "resolved", "wins", "losses", "pnl_usd", "win_rate"];
  target.innerHTML = keys.map((key) => (
    `<div class="metric"><span>${label(key)}</span><strong>${escapeHtml(String(summary[key] ?? ""))}</strong></div>`
  )).join("");
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function refresh() {
  try {
    const response = await fetch(`/api/state?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    latestData = data;
    render(data);
  } catch (error) {
    document.getElementById("updated").innerHTML = `<span class="error">Dashboard error: ${escapeHtml(error.message)}</span>`;
  }
}

function render(data) {
    document.getElementById("updated").textContent =
      `updated=${data.updated_at} latest_snapshot=${data.health.latest_snapshot || "none"} refresh=10s`;
    renderStatus(data.health);
    renderSummary(data.trade_summary || {});
    renderProofCalibration(data.proof_of_winning_calibration_summary || {});
    renderSpreadCalibration(data.spread_confirmation_calibration_summary || {});
    renderGoalTotalsUnderCalibration(data.goal_totals_under_calibration_summary || {});
    const enrichedPregame = enrichTimeRows(data.pregame);
    const stillPregame = enrichedPregame.filter((row) => Number(row.minutes_to_start) >= 0);
    const kickoffPassedFromPregame = enrichedPregame.filter((row) => {
      const minutes = Number(row.minutes_to_start);
      return Number.isFinite(minutes) && minutes < 0 && !row.confirmed_by_sports_api;
    }).map((row) => ({
      ...row,
      live_source: row.live_source || "polymarket_start_time_unconfirmed",
      status_note: row.status_note || "visible_only_no_trade_until_sports_api_confirms",
    }));
    const fallbackUnconfirmed = (data.pregame || []).filter((row) => {
      const minutes = Number(row.minutes_to_start);
      return Number.isFinite(minutes) && minutes < 0 && minutes >= -20 && !row.confirmed_by_sports_api;
    }).map((row) => ({
      ...row,
      live_source: row.live_source || "polymarket_start_time_unconfirmed",
      time_source: row.time_source || "polymarket_start_time",
      confirmed_match_minute: row.confirmed_match_minute || "",
      status_note: row.status_note || "waiting_for_live_api_no_trade",
    }));
    const viewData = {
      ...data,
      pregame: stillPregame,
      unconfirmed_started: (data.unconfirmed_started && data.unconfirmed_started.length > 0)
        ? enrichTimeRows([...data.unconfirmed_started, ...kickoffPassedFromPregame])
        : kickoffPassedFromPregame.length ? kickoffPassedFromPregame : fallbackUnconfirmed,
      unmatched_diagnostic: enrichTimeRows(data.unmatched_diagnostic),
    };
    Object.entries(sections).forEach(([id, columns]) => renderTable(id, viewData[id], columns));
}

refresh();
setInterval(refresh, REFRESH_MS);
setInterval(() => {
  if (latestData && latestData.updated_at) render(latestData);
}, 1000);
