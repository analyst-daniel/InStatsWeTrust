# Goal Totals Under — Etap 6

## Cel etapu

Podlaczyc strategie `goal_totals_under` do realnego pipeline paper trading.

Od tego etapu:

- rynek `total` wchodzi do osobnej logiki runtime,
- `UNDER` moze otworzyc paper trade,
- `OVER` jest blokowany przez osobny reason code,
- decyzja zapisuje sie przez standardowy `entry_reason`.

## Zakres

Dodany runtime:

- `GoalTotalsUnderRuntime`

Runtime:

1. przyjmuje `market`, `observation`, `live_state`,
2. dziala tylko dla `market_type == total`,
3. laduje historyczne detale meczu z `FootballResearchStore`,
4. buduje input totals,
5. hydratuje rolling metrics 5m / 10m,
6. liczy stabilnosc pre-stability na historii,
7. wywoluje `goal_totals_under_enter_decision_v1`,
8. zwraca:
   - `applies`
   - `enter`
   - `reason`
   - `payload`

## Wpiecie do skanera

`run_scanner.py` po bazowej kwalifikacji cenowej uruchamia teraz kolejno:

1. `spread_confirmation`
2. `proof_of_winning`
3. `goal_totals_under`

Dla rynku totals:

- `goal_totals_under` nadpisuje `observation.reason`
- i decyduje, czy wejscie zostaje utrzymane

## Nowe reason codes runtime

- `goal_totals_under_missing_live_state`
- `goal_totals_under_missing_fixture_id`
- `goal_totals_under_missing_detail_history`
- `goal_totals_under_missing_score_context`
- `goal_totals_under_wrong_side`
- `goal_totals_under_enter`

plus wszystkie reason codes z etapow 4-5.

## Efekt etapu

Po etapie 6:

- `UNDER` nie jest juz tylko debug metadata,
- tylko moze realnie otwierac paper trade,
- ale wyłącznie po przejsciu przez logike aktywacji, presji, chaosu i stabilnosci.
