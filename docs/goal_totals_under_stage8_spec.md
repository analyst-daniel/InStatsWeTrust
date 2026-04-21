# Goal Totals Under — Etap 8

## Cel etapu

Domknac kalibracje strategii `goal_totals_under` na tych samych zasadach, co `proof_of_winning` i `spread_confirmation`.

Od tego etapu strategia `UNDER` ma:

- summary wynikow,
- grupowanie po linii totals,
- grupowanie po minucie wejscia,
- grupowanie po lidze,
- grupowanie po `entry_reason`.

## Zakres

Dodany modul:

- `goal_totals_under_calibration.py`

Dashboard zwraca teraz:

- `goal_totals_under_calibration_summary`
- `goal_totals_under_calibration_line`
- `goal_totals_under_calibration_entry_bucket`
- `goal_totals_under_calibration_league`
- `goal_totals_under_calibration_reason`

## Co pokazuje kalibracja

### Summary

- total
- resolved
- wins
- losses
- pnl_usd
- win_rate

### By line

Przyklady grup:

- `2.5`
- `3.5`
- `4.5`

### By entry bucket

Przyklady grup:

- `75-79`
- `80-84`
- `85-88`

### By league

Liga jest wyciagana z `event_slug`, zgodnie z mapowaniem uzywanym juz w innych strategiach.

### By reason

Pozwala sprawdzic, czy w przyszlosci nie rozjezdzaja sie rozne wersje wejscia lub dodatkowe reason codes.

## Efekt etapu

Po etapie 8:

- `UNDER` ma zamkniety tor test + debug + calibration,
- mozna porownywac wyniki po:
  - linii,
  - minucie wejscia,
  - lidze,
  - reason code.
