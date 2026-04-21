# Goal Totals Under — Etap 5

## Cel etapu

W tym etapie dokładamy pierwszą twardą logikę wejścia `ENTER / NO ENTER` dla strategii `UNDER`.

Etap 5 nie uruchamia jeszcze pełnej integracji runtime. To jest warstwa decyzyjna:

1. aktywacja marketu `UNDER`,
2. ocena presji i chaosu,
3. rozróżnienie przypadków:
   - `strict mode` dla buforu `< 2.0`,
   - `standard mode` dla buforu `>= 2.0`,
4. wymaganie stabilności przez kolejne snapshoty.

## Zasady wejścia v1

Najpierw market musi przejść etap aktywacji:

- minuta w oknie `70 <= minute < 89`
- poprawny market `O/U`
- wybrana strona to `UNDER`
- `data_confidence_flag = TRUE`
- brak czerwonej kartki
- `goal_buffer >= 1.0`

Potem dokładamy filtry wejścia:

- brak gola w ostatnich 3 lub 5 minutach
- brak rosnącego trendu presji:
  - `pressure_trend_last_10 != up`
  - `shots_trend_last_10 != up`
  - `dangerous_attacks_trend_last_10 != up`
- brak rosnącego tempa:
  - `tempo_change_last_10 != up`

## Strict mode

Strict mode działa, gdy:

- `goal_buffer < 2.0`

Progi:

- `shots_last_10 <= 2`
- `shots_on_target_last_10 <= 0`
- `corners_last_10 <= 1`
- `dangerous_attacks_last_10 <= 5`
- `total_shots_both_last_10 <= 3`
- `total_dangerous_attacks_both_last_10 <= 8`
- `total_corners_both_last_10 <= 2`

## Standard mode

Standard mode działa, gdy:

- `goal_buffer >= 2.0`

Progi:

- `shots_last_10 <= 3`
- `shots_on_target_last_10 <= 1`
- `corners_last_10 <= 2`
- `dangerous_attacks_last_10 <= 8`
- `total_shots_both_last_10 <= 5`
- `total_dangerous_attacks_both_last_10 <= 12`
- `total_corners_both_last_10 <= 3`

## Stabilność sygnału

Pełne wejście `ENTER` jest dozwolone tylko wtedy, gdy:

- `stable_for_2_snapshots = TRUE`
  lub
- `stable_for_3_snapshots = TRUE`

Jeżeli warunki presji/chaosu są OK, ale stabilności jeszcze nie ma, funkcja pre-stability zwraca:

- `goal_totals_under_pre_stability_ok`

A pełna funkcja wejścia zwraca:

- `goal_totals_under_no_enter_not_stable`

## Powody odrzucenia

Najważniejsze reason codes w etapie 5:

- `goal_totals_under_no_enter_recent_goal`
- `goal_totals_under_no_enter_pressure`
- `goal_totals_under_no_enter_chaos`
- `goal_totals_under_no_enter_not_stable`
- `goal_totals_under_enter`

## Co jeszcze nie jest w etapie 5

Jeszcze nie wdrażamy tutaj:

- runtime paper trade dla `UNDER`
- zapisu wejść `UNDER` do osobnego debug/calibration flow
- pełnego dashboardu dla `UNDER`
- dodatkowych filtrów typu possession / fouls / substitutions

To będzie w kolejnych etapach.
