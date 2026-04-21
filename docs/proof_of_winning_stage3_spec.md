# Proof Of Winning Stage 3 Spec

Etap 3 buduje rolling metrics 5m / 10m na bazie historii snapshotow detail per fixture.

## Cel etapu

Policzyc dynamiczne metryki dla strategii `proof_of_winning`, zamiast opierac sie na pojedynczym `latest.json`.

## Co zostalo wdrozone

### 1. Historia detail snapshotow per fixture

Plik:
- `app/live_state/football_research.py`

Zmiana:
- poza `latest.json` zapisywany jest tez historyczny plik:
  - `detail_YYYYMMDDTHHMMSSZ.json`

To daje podstawe do porownan:
- current vs 5 minut temu
- current vs 10 minut temu
- last 5 vs previous 5

### 2. Kalkulator rolling metrics

Plik:
- `app/strategy/proof_of_winning_metrics.py`

Funkcje:
- `build_rolling_metrics(detail_history)`
- `populate_input_with_metrics(base, metrics)`

## Jak liczone sa metryki

### Shots / shots on target / corners / dangerous attacks

Sa liczone jako roznica miedzy:
- aktualnym snapshotem statystyk
- a najblizszym snapshotem sprzed `5` lub `10` minut meczu

Przyklad:
- minuta 78
- baseline 5m = snapshot z `<= 73`
- baseline 10m = snapshot z `<= 68`

### Trend

Trend porownuje:
- `last 5`
vs
- `previous 5`

Interpretacja:
- `up`
- `down`
- `stable`
- `unknown`

### Chaos flags

Na podstawie `events` liczone sa:
- `goal_in_last_3min`
- `goal_in_last_5min`
- `red_card_in_last_10min`
- `time_since_last_goal`

## Wynik kalkulatora

Model:
- `RollingMetrics`

Zawiera:

### trailing team
- `shots_last_5`
- `shots_on_target_last_5`
- `shots_last_10`
- `shots_on_target_last_10`
- `dangerous_attacks_last_5`
- `dangerous_attacks_last_10`
- `corners_last_5`
- `corners_last_10`

### match
- `total_shots_both_last_10`
- `total_dangerous_attacks_both_last_10`
- `total_corners_both_last_10`
- `goal_in_last_3min`
- `goal_in_last_5min`
- `red_card_in_last_10min`
- `time_since_last_goal`

### trend
- `pressure_trend_last_10`
- `shots_trend_last_10`
- `dangerous_attacks_trend_last_10`
- `tempo_change_last_10`

### data quality
- `source_fields_present`
- `data_confidence_flag`

## Jak ustawiany jest data confidence

Na obecnym etapie:
- `data_confidence_flag = TRUE`
gdy mamy komplet minimalnych pol:
  - `shots_last_5`
  - `shots_last_10`
  - `shots_on_target_last_10`
  - `dangerous_attacks_last_10`
  - `corners_last_10`

## Co jeszcze nie jest zrobione

Etap 3 jeszcze nie podejmuje finalnej decyzji `ENTER / NO ENTER`.

To bedzie Etap 4:
- V1 hard filters
- presja trailing team
- chaos
- trend
- stability gate

## Testy

Plik:
- `tests/test_proof_of_winning_metrics.py`

Pokryte:
- last 5 / last 10 z historii detaili
- trend dla shots i dangerous attacks
- chaos flags z events
- hydracja `ProofOfWinningInput`
