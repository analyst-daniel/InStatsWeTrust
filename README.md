# Polymarket Self Hosted

Live Polymarket soccer scanner, paper trading system and dry-run execution checker.

The bot does not place real orders. Current execution mode is `dry_run`: it can check the real Polymarket orderbook and simulate whether an order could be filled, but live order placement is intentionally disabled.

## Start

Open PowerShell:

```powershell
cd C:\Users\Daniel\Desktop\POLY_BET\polymarket_self_hosted
.\restart_all_windows.bat
```

This restarts the whole system:

- live state
- Football API fallback
- scanner / paper trader / dry-run execution
- settlement
- dashboard

Dashboard:

```text
http://127.0.0.1:8765
```

After code or dashboard layout changes, refresh the browser with `Ctrl+F5`.

## Stop

```powershell
cd C:\Users\Daniel\Desktop\POLY_BET\polymarket_self_hosted
.\stop_all_windows.bat
```

## One-Off Commands

Run one scanner cycle:

```powershell
.\scan_once.bat
```

Run settlement once:

```powershell
.\settlement_once.bat
```

Create daily report:

```powershell
.\daily_report.bat
```

## Current Logic

Main strategy config is in:

```text
config/settings.yaml
```

Important current assumptions:

- soccer only
- normal entry window: `70 <= minute < 89`
- dry-run execution is enabled
- real live execution is disabled
- runs start from `10` units
- run target is `21` units
- current dashboard run calculation uses the user run method:
  - start run at `10`
  - bet all current run capital
  - first lost closes the run
  - reaching `21` closes the run as win

## Dashboard KPI

Right-side KPI uses run-based units:

- `Hold`: run result if every trade is held to settlement
- `Full exit`: run result with full V2 exit
- `50% exit`: run result with half V2 exit
- `Liquidity exit`: run result using confirmed exit liquidity

The `Runs` section also uses the same run method.

## Data Files

Main files:

```text
data/snapshots/trade_log.csv
data/snapshots/snapshot_log.csv
data/snapshots/under_buffer_exit_log.csv
data/snapshots/execution_log.csv
data/db/polymarket_self_hosted.sqlite
data/logs/system.log
data/logs/errors.log
data/daily/
```

`execution_log.csv` appears only after a strategy signal reaches the dry-run execution stage.

## Safety

Do not put real funds into this system.

`execution.mode: live` is intentionally blocked in code. If enabled by mistake, the scanner should stop with an error instead of placing a real order.
