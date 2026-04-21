## Etap 3 - Rolling metrics 5m / 10m dla obu druzyn

Cel etapu:

- policzyc rolling metrics osobno dla lidera i underdoga,
- zbudowac warstwe chaosu i trendu dla strategii spread,
- przygotowac surowe dane pod Etap 4 (`spread_plus`) i Etap 5 (`spread_minus`).

Zakres:

1. Nowy modul:
   - `app/strategy/spread_confirmation_metrics.py`

2. Dane dla lidera:
   - `leader_shots_last_5`
   - `leader_shots_on_target_last_5`
   - `leader_shots_last_10`
   - `leader_shots_on_target_last_10`
   - `leader_dangerous_attacks_last_5`
   - `leader_dangerous_attacks_last_10`
   - `leader_corners_last_5`
   - `leader_corners_last_10`

3. Dane dla underdoga:
   - `underdog_shots_last_5`
   - `underdog_shots_on_target_last_5`
   - `underdog_shots_last_10`
   - `underdog_shots_on_target_last_10`
   - `underdog_dangerous_attacks_last_5`
   - `underdog_dangerous_attacks_last_10`
   - `underdog_corners_last_5`
   - `underdog_corners_last_10`

4. Chaos:
   - `total_shots_both_last_10`
   - `total_dangerous_attacks_both_last_10`
   - `total_corners_both_last_10`
   - `goal_in_last_3min`
   - `goal_in_last_5min`
   - `red_card_in_last_10min`
   - `time_since_last_goal`

5. Trend:
   - `leader_pressure_trend_last_10`
   - `underdog_pressure_trend_last_10`
   - `shots_trend_last_10`
   - `dangerous_attacks_trend_last_10`
   - `tempo_change_last_10`

6. Wynik etapu:
   - `SpreadConfirmationInput` mozna nawodnic rolling metrics dla obu stron meczu
   - decyzje `spread_plus` i `spread_minus` nie musza juz bazowac tylko na wyniku
