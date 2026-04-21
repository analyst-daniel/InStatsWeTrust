# Goal Totals Under Stage 1

## Cel
Zamknac definicje inputu i parsera rynku totals dla strategii `goal_totals_under`.

## Zakres

1. Dodac parser rynku totals:
   - wykrywa `O/U X.Y`
   - rozpoznaje strone:
     - `Under`
     - `Over`
2. Strategia ma byc przygotowana tylko pod `Under`.
3. Zbudowac bazowy model inputu:
   - minute
   - score
   - total_goals
   - total_line
   - goal_buffer
   - selected_side_type
   - data_confidence_flag
   - red_card_flag
4. Dodac bucket czasu:
   - `70_74`
   - `75_85`
   - `86_88`
   - `outside`

## Ważne zasady

- parser totals moze rozpoznac `Over`, ale strategia docelowo ma grac tylko `Under`
- `goal_buffer = total_line - total_goals`
- okno aktywacji etapu 1:
  - `70 <= minute < 89`

## Oczekiwany efekt

- dla `Under 3.5` przy wyniku `2:0`:
  - `total_goals = 2`
  - `goal_buffer = 1.5`
- dla `Over 3.5` parser dalej rozpoznaje rynek, ale input wie, ze to nie jest `Under`
- dane sa gotowe pod etap 2 i 3
