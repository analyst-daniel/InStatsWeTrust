# Goal Totals Under Stage 4

## Cel
Wdrozyc twarde warunki aktywacji dla strategii `goal_totals_under`.

## Zakres

1. Dodac osobna decyzje aktywacji:
   - `GoalTotalsUnderActivationDecision`
2. Aktywacja tylko gdy:
   - `minute >= 70`
   - `minute < 89`
   - rynek jest poprawnym totals market
   - strona = `Under`
   - `data_confidence_flag = TRUE`
   - brak czerwonej kartki
   - `goal_buffer >= 1.0`
3. Zwracac osobne reason codes.
4. Rozroznic bucket czasu:
   - `70_74`
   - `75_85`
   - `86_88`

## Przykladowe reason codes

- `goal_totals_under_activation_ok_70_74`
- `goal_totals_under_activation_ok_75_85`
- `goal_totals_under_activation_ok_86_88`
- `goal_totals_under_wrong_side`
- `goal_totals_under_buffer_too_small`
- `goal_totals_under_red_card`
- `goal_totals_under_low_data_confidence`
- `goal_totals_under_minute_outside_window`
- `goal_totals_under_invalid_totals_market`

## Ważne

- to jeszcze nie jest logika `ENTER / NO ENTER` z metryk
- to jest tylko decyzja:
  - czy `UNDER` w ogole kwalifikuje sie do dalszej analizy

## Oczekiwany efekt

- `Over` jest odrzucany od razu
- `Under` z buforem `< 1.0` jest odrzucany od razu
- poprawne `Under` przechodza dalej z bucketem czasu
