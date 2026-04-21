# Goal Totals Under Stage 3

## Cel
Zbudowac rolling metrics `5m / 10m` pod logike `UNDER`.

## Zakres

1. Wyliczac dla calego meczu:
   - `shots_last_5`
   - `shots_on_target_last_5`
   - `shots_last_10`
   - `shots_on_target_last_10`
   - `dangerous_attacks_last_5`
   - `dangerous_attacks_last_10`
   - `attacks_last_5`
   - `attacks_last_10`
   - `corners_last_5`
   - `corners_last_10`
2. Wyliczac chaos:
   - `total_shots_both_last_10`
   - `total_dangerous_attacks_both_last_10`
   - `total_corners_both_last_10`
   - `goal_in_last_3min`
   - `goal_in_last_5min`
   - `red_card_in_last_10min`
3. Wyliczac trend:
   - `pressure_trend_last_10`
   - `shots_trend_last_10`
   - `dangerous_attacks_trend_last_10`
   - `tempo_change_last_10`
4. Umiec wstrzyknac te pola do `GoalTotalsUnderInput`.

## Ważne

- w etapie 3 nie ma jeszcze decyzji `ENTER / NO ENTER`
- to jest tylko warstwa metryk pod etapy 4 i 5
- `shots` i `dangerous_attacks` traktujemy jako proxy zycia ofensywnego meczu

## Oczekiwany efekt

- mamy lokalne rolling context `5m / 10m`
- input strategii `UNDER` zawiera komplet pol do:
  - presji
  - chaosu
  - trendu
  - stabilnosci
