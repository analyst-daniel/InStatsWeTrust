# Spread Confirmation Stage 6

## Cel
Podpiac `spread_confirmation` do realnego skanera i paper tradera, tak zeby markety spread nie byly juz otwierane tylko na podstawie:

- ceny 0.95-0.99,
- minuty 75+,
- potwierdzenia 2 scanami.

Od tego etapu spread musi przejsc dodatkowo przez runtime oparty o:

- szczegoly live z Football API,
- rolling metrics last 5 / last 10,
- logike `spread_plus_v1` lub `spread_minus_v1`,
- stability requirement.

## Zakres

1. Dodac `SpreadConfirmationRuntime`.
2. Uzywac runtime w `scripts/run_scanner.py` przed paper trade.
3. Dla marketow `spread`:
   - `applies=True`
   - decyzja wejscia ma pochodzic z `spread_confirmation`.
4. Zachowac stare zachowanie dla innych typow marketow.
5. Poprawic `entry_reason`, zeby nie gubil informacji o strategii po hold-confirm.
6. Poprawic insert snapshotow do SQLite przez jawna liste kolumn.

## Oczekiwane efekty

- `Iwaki FC -2.5` przy wyniku `1:0` nie moze wejsc.
- `+1.5` moze wejsc, jezeli przejdzie plus-logike i stabilnosc.
- reason w trade log ma zawierac warstwe strategii, np.:
  - `spread_minus_margin_too_small_price_held_...`
  - `spread_plus_enter_price_held_...`
- snapshoty dalej zapisuja spread metadata bez ryzyka rozjazdu kolumn.

## Testy

- runtime blokuje `-2.5` przy zbyt malym marginesie,
- runtime przepuszcza poprawny `+1.5`,
- istniejące testy spread/proof dalej przechodza.
