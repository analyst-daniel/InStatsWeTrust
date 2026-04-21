# Goal Totals Under Stage 2

## Cel
Dodac do lokalnych snapshotow surowe metadata totals potrzebne do dalszej logiki `goal_totals_under`.

## Zakres

1. Rozszerzyc `MarketObservation` o pola totals:
   - `total_line`
   - `total_selected_side_type`
   - `total_goals`
   - `total_goal_buffer`
2. Rozszerzyc tabele `snapshots` w SQLite o te pola.
3. Wypelniac te pola w `StrategyEngine` dla kazdego totals marketu.

## Ważne

- to nie uruchamia jeszcze strategii `Under`
- to tylko przygotowuje warstwe danych
- `Over` dalej moze byc zapisane w snapshotcie, ale pozniejsze etapy beda je odrzucac

## Oczekiwany efekt

Przykladowo dla:

- pytanie: `... O/U 3.5`
- side: `Under`
- score: `2-0`

snapshot ma miec:

- `total_line = 3.5`
- `total_selected_side_type = under`
- `total_goals = 2`
- `total_goal_buffer = 1.5`
