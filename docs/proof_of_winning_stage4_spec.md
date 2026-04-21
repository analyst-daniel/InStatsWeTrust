# Proof Of Winning Stage 4 Spec

Etap 4 wdraza pierwsza wersje decyzyjna `ENTER / NO ENTER` dla strategii `proof_of_winning_v1`.

## Cel etapu

Na bazie:
- aktywacji z Etapu 1
- rolling metrics z Etapu 3

zwracac:
- `ENTER`
- `NO ENTER`

z jednoznacznym reason code.

## Co zostalo wdrozone

Plik:
- `app/strategy/proof_of_winning.py`

Nowe elementy:
- `EnterDecision`
- `enter_decision_v1(data)`

## Kolejnosc filtrow

### 1. Activation gate

Najpierw przechodzi:
- `activation_decision(data)`

Jesli aktywacja nie przejdzie:
- wynik = `NO ENTER`
- reason = reason z aktywacji

### 2. Filtr presji trailing team

Automatyczny `NO ENTER`, gdy:

- `shots_last_10 >= 4`
- `shots_on_target_last_10 >= 2`
- `corners_last_10 >= 3`
- `dangerous_attacks_last_10 >= 8`

### 3. Filtr trendu

Automatyczny `NO ENTER`, gdy:

- `pressure_trend_last_10 == up`
- `shots_trend_last_10 == up`
- `dangerous_attacks_trend_last_10 == up`

### 4. Filtr chaosu

Automatyczny `NO ENTER`, gdy:

- `goal_in_last_3min = TRUE`
- `red_card_in_last_10min = TRUE`
- `tempo_change_last_10 == up`

### 5. Stability requirement

Automatyczny `NO ENTER`, gdy:

- `stable_for_2_snapshots = FALSE`
- i `stable_for_3_snapshots = FALSE`

### 6. ENTER

Jesli wszystkie filtry przejda:

- wynik = `ENTER`
- reason = `proof_of_winning_enter`

## Reason codes

### Activation / hard gate

- `proof_of_winning_minute_outside_window`
- `proof_of_winning_goal_difference_too_low`
- `proof_of_winning_leader_red_card`
- `proof_of_winning_low_data_confidence`
- `proof_of_winning_missing_required_fields`

### Pressure

- `proof_of_winning_no_enter_pressure_shots_last_10`
- `proof_of_winning_no_enter_pressure_shots_on_target_last_10`
- `proof_of_winning_no_enter_pressure_corners_last_10`
- `proof_of_winning_no_enter_pressure_dangerous_attacks_last_10`

### Trend

- `proof_of_winning_no_enter_trend_pressure_up`
- `proof_of_winning_no_enter_trend_shots_up`
- `proof_of_winning_no_enter_trend_dangerous_attacks_up`

### Chaos

- `proof_of_winning_no_enter_chaos_goal_last_3min`
- `proof_of_winning_no_enter_chaos_red_card_last_10min`
- `proof_of_winning_no_enter_chaos_tempo_up`

### Stability

- `proof_of_winning_no_enter_not_stable`

### Success

- `proof_of_winning_enter`

## Co jeszcze nie jest zrobione

Etap 4 jeszcze nie:
- podpina tej logiki pod skaner i paper trading
- nie porownuje `proof_of_winning` z obecna strategia live
- nie loguje tych decyzji do snapshot table jako osobnej strategii

To bedzie etap integracyjny pozniej.

## Testy

Plik:
- `tests/test_proof_of_winning.py`

Pokryte:
- poprawny ENTER
- NO ENTER przy presji
- NO ENTER przy trendzie up
- NO ENTER przy chaosie
- NO ENTER przy braku stabilnosci
