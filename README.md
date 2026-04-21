# Polymarket Self Hosted

Standalone read-only Polymarket sports scanner and paper-trading system.

This project does not use Bullpen and does not place real orders. It uses public/no-auth Polymarket endpoints for discovery, live sports state, and market data. Real execution is only scaffolded in `app/execution/` and intentionally disabled.

## Setup

```powershell
cd C:\Users\Daniel\Desktop\POLY_BET\polymarket_self_hosted
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If you do not use a venv, run the same scripts with your system Python.

## Run Flow

Terminal 1, live sports state:

```powershell
cd C:\Users\Daniel\Desktop\POLY_BET\polymarket_self_hosted
.\.venv\Scripts\Activate.ps1
python scripts\run_live_state.py
```

Terminal 2, scanner and paper trader:

```powershell
cd C:\Users\Daniel\Desktop\POLY_BET\polymarket_self_hosted
.\.venv\Scripts\Activate.ps1
python scripts\run_scanner.py
```

Terminal 3, dashboard:

```powershell
cd C:\Users\Daniel\Desktop\POLY_BET\polymarket_self_hosted
.\.venv\Scripts\Activate.ps1
python scripts\run_dashboard.py
```

Terminal 4, settlement and daily reports:

```powershell
cd C:\Users\Daniel\Desktop\POLY_BET\polymarket_self_hosted
.\.venv\Scripts\Activate.ps1
python scripts\run_settlement.py
```

Optional Football API fallback for live soccer minute/score:

```powershell
setx APISPORTS_KEY "your_api_key_here"
# open a new terminal after setx
cd C:\Users\Daniel\Desktop\POLY_BET\polymarket_self_hosted
.\.venv\Scripts\Activate.ps1
python scripts\run_football_fallback.py
```

Batch shortcuts are also available:

```powershell
start_live_state.bat
start_football_fallback.bat
start_scanner.bat
start_settlement.bat
start_dashboard.bat
scan_once.bat
settlement_once.bat
daily_report.bat
```

## Strategy Defaults

Configured in `config/settings.yaml`:

- sport: soccer
- elapsed: `75 <= elapsed < 89`
- price: `0.95 <= ask < 0.99`
- stake: `$10`
- max entries per market: `5`
- no paper entry without live state
- real execution disabled

The scanner logs all observed markets in the target price range to the snapshot log. It opens paper trades only when live state and risk rules pass.

## Data

- `data/raw/`: raw Gamma API responses
- `data/snapshots/snapshot_log.csv`: all observed qualifying price-range markets
- `data/snapshots/trade_log.csv`: paper trades only
- `data/snapshots/live_state_cache.json`: latest Sports WebSocket state
- `data/snapshots/football_api_budget.json`: daily API-FOOTBALL request budget counter
- `data/db/polymarket_self_hosted.sqlite`: queryable dashboard database
- `data/logs/system.log`: runtime logs
- `data/logs/errors.log`: errors
- `data/daily/trade_report_YYYY-MM-DD.csv`: daily paper trade export
- `data/daily/summary_YYYY-MM-DD.md`: daily summary

## Public No-Auth Sources

- Gamma REST: `https://gamma-api.polymarket.com/events`, `/markets`, `/public-search`
- Sports WebSocket: `wss://sports-api.polymarket.com/ws`
- CLOB public REST: `https://clob.polymarket.com/book`, `/books`, `/price`, `/prices`, `/spreads`, `/last-trades-prices`
- CLOB market WebSocket: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Data API research endpoint: `https://data-api.polymarket.com/trades`

## Future Real Trading

Authenticated CLOB execution would be inserted under `app/execution/`. It must add credentials, signing, geoblock pre-checks, order validation, kill switch enforcement, and explicit enablement. The current code raises an exception for real order placement.
