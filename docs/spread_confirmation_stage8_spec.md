# Spread Confirmation Stage 8

## Cel
Sprawdzic, czy progi `spread_confirmation` maja sens na realnych tradeach i pokazac to w dashboardzie.

## Zakres

1. Dodac kalibracje dla tradeow `spread_`.
2. Wyliczac:
   - total
   - resolved
   - wins
   - losses
   - pnl_usd
   - win_rate
3. Grupowac wyniki:
   - po lidze
   - po bucket minuty wejscia
   - po linii spreadu
   - po typie strony spreadu (`plus` / `minus`)
4. Dodac sekcje `Spread Confirmation Calibration` do dashboardu.
5. Dodac testy dla helperow i podsumowan.

## Oczekiwany efekt

- widac osobno, jak zachowuja sie:
  - `+1.5`
  - `-1.5`
  - `+2.5`
  - `-2.5`
- widac, czy lepiej dzialaja wejscia `plus` czy `minus`
- widac, czy wyniki roznia sie po lidze i minucie wejscia

## Uwagi

- to jest kalibracja na podstawie faktycznie zawartych tradeow,
- nie na podstawie wszystkich odrzuconych case,
- debug odrzuconych case zostaje w `Spread Confirmation Debug`.
