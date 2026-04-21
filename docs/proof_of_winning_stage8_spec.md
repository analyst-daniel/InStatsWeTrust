## Etap 8 - Testy i Kalibracja

Cel etapu:

- domknac testy regresyjne strategii,
- zbudowac pierwszy raport kalibracyjny na realnych trade logach,
- pokazac kluczowe grupowania w dashboardzie.

Zakres:

1. Testy:
   - potwierdzenie aktywacji tylko w `75 <= minute < 89`
   - odrzucenie przy red card lidera
   - odrzucenie przy wysokiej presji
   - odrzucenie przy chaosie
   - odrzucenie przy braku stabilnosci
   - odrzucenie przy braku historii / danych

2. Kalibracja:
   - filtr tylko dla trade z `entry_reason` zaczynajacym sie od `proof_of_winning`
   - summary:
     - total
     - resolved
     - wins
     - losses
     - pnl_usd
     - win_rate
   - grupowania:
     - po lidze
     - po bucket minute wejscia
     - po typie marketu
     - po reason code

3. Dashboard:
   - sekcja `Proof Of Winning Calibration`
   - summary grid
   - tabele:
     - by market type
     - by entry bucket
     - by league

4. CLI:
   - skrypt do generacji raportu markdown/csv z SQLite
   - output do `data/daily`
