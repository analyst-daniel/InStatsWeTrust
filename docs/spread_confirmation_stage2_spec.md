## Etap 2 - Warstwa surowych danych meczowych

Cel etapu:

- zapisac parsed spread metadata razem ze snapshotem,
- miec surowe dane potrzebne do dalszej logiki i debugowania,
- uniknac ponownego parsowania historycznych snapshotow z samego `question`.

Zakres:

1. Rozszerzenie `MarketObservation` o pola:
   - `market_type`
   - `spread_listed_team`
   - `spread_listed_line`
   - `spread_listed_side_type`
   - `spread_selected_team`
   - `spread_selected_line`
   - `spread_selected_side_type`

2. Przy tworzeniu snapshotu:
   - parser spreadu uruchamia sie juz na etapie `StrategyEngine`
   - snapshot zapisuje nie tylko `question`, ale tez wynik parsowania

3. Storage:
   - tabela `snapshots` w SQLite wspiera nowe kolumny
   - CSV snapshot log rowniez zawiera te pola
   - migracja jest kompatybilna ze starym plikiem przez `ALTER TABLE` i elastyczny CSV rewrite

4. Wynik etapu:
   - historyczne snapshoty maja juz parsed spread metadata
   - mozemy w Etapie 3 i dalej korzystac z surowych pol zamiast parsowac `question` na nowo
