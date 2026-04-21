# Spread Confirmation Stage 7

## Cel
Pokazac w dashboardzie, dlaczego konkretny spread:

- wszedl,
- albo nie wszedl.

Bez zgadywania i bez recznego odtwarzania snapshotow.

## Zakres

1. Dodac sekcje `Spread Confirmation Debug` do dashboardu webowego.
2. Dodac ten sam podglad do terminal dashboardu.
3. Dla spread row pokazac:
   - minute
   - score
   - spread_line
   - spread_side_type
   - aktualny margines
   - leader stats last 10
   - underdog stats last 10
   - pressure trends
   - chaos flags
   - stability flags
   - final decision
   - rejection reason
4. Oprzec to na runtime `spread_confirmation`, nie na samym snapshot reason.

## Oczekiwany efekt

- dla `-2.5` przy `1:0` widac wprost:
  - `final_decision = NO ENTER`
  - `rejection_reason = spread_minus_margin_too_small`
- dla poprawnych case widac:
  - `ENTER`
  - minute
  - line
  - selected_team_margin
  - live statsy i stabilnosc

## Test

- debug row dla spreadu musi zwracac:
  - decyzje,
  - powod,
  - line,
  - side type,
  - selected_team_margin.
