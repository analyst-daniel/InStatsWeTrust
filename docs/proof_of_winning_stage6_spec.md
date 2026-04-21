## Etap 6 - Runtime Integration

Cel etapu 6:

- podpiac `proof_of_winning` do glownego skanera,
- budowac wejscie strategii z:
  - live state,
  - znormalizowanego marketu Polymarket,
  - historii detali z Football API,
- zapisywac finalny `entry_reason` do snapshotow i paper trade,
- utrzymac zgodnosc CSV/SQLite przy rozszerzonym schemacie trade.

Zakres:

1. `ProofOfWinningRuntime`
   - sprawdza czy market jest rynkiem typu winner,
   - mapuje `Yes` na lidera i `No` na druzyne przegrywajaca,
   - pobiera historie detali fixture z Football API,
   - liczy rolling metrics,
   - liczy effective goal difference,
   - ocenia stabilnosc na 2-3 kolejnych snapshotach,
   - zwraca finalna decyzje `ENTER / NO ENTER` wraz z reason code.

2. Integracja ze skanerem
   - proof-of-winning uruchamia sie tylko dla marketow, do ktorych pasuje,
   - finalny `reason` ma trafiać do snapshotu i trade,
   - paper trader ma zapisywac `entry_reason`.

3. Storage
   - `entry_reason` ma byc wspierane w SQLite i CSV,
   - rewrite CSV nie moze sie wykladac na starych wierszach bez nowej kolumny,
   - historia Football API ma zapisywac kazdy detal snapshot osobno, bez nadpisywania plikow.

4. Testy
   - runtime test dla pozytywnego przypadku ENTER,
   - runtime test dla braku historii,
   - runtime test dla marketu, do ktorego strategia nie ma zastosowania.
