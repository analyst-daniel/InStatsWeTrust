# Strategy Cheatsheet

Aktualny stan systemu paper tradingu. Dokument opisuje, jakie typy rynkow sa grane i co musi byc spelnione, zeby bot otworzyl pozycje.

## Globalne warunki wejscia

Kazda pozycja musi najpierw przejsc wspolne filtry:

- Sport musi byc `soccer`.
- Market musi byc aktywny i niezamkniety.
- Musi byc dopasowany live state meczu.
- Mecz musi byc live, nie zakonczony.
- Minuta meczu musi byc `>= 70` i `< 89`.
- Cena wejscia musi byc `>= 0.60` i `<= 0.99`.
- Spread orderbooka nie moze byc wiekszy niz `1.0`.
- Liquidity minimum jest aktualnie `0`, czyli brak realnego filtra liquidity.
- Cena musi utrzymac sie przez `5s` (`min_price_hold_seconds`).
- Risk manager musi pozwolic na wejscie:
  - dzienny limit paper trade'ow jest praktycznie wylaczony (`1000000`),
  - limit otwartych pozycji jest praktycznie wylaczony (`1000000`),
  - max `5` wejsc na jeden market,
  - brak duplikatu na ten sam otwarty outcome,
  - cooldown `60s` na market,
  - `kill_switch` musi byc `false`.

## Rynki blokowane

Te rynki sa obecnie blokowane przed wejsciem:

- `Halftime Result` oraz wszystko z `halftime` w pytaniu lub tytule.
- Corners.
- Anytime goalscorer / goalscorer.
- Exact score.
- Both Teams To Score.
- Future goal event, np. `next goal`, `another goal`, `any more goals`, `will there be a goal`, `to score a goal`.
- Draw `Yes`.

## No Draw

Rynek typu:

`Will Team A vs. Team B end in a draw?`

Gramy tylko strone `No`.

Warunki:

- Musi przejsc globalne filtry.
- Strona `Yes` jest zawsze blokowana.
- Score musi byc znany.
- Roznica goli musi byc minimum `2`.
- Nie ma obecnie osobnego runtime z live statystykami dla `No Draw`.
- Nie ma obecnie filtra `recent goal` dla `No Draw`.
- Nie ma obecnie filtra presji underdoga dla `No Draw`.

Przyklad dozwolony:

- `2-0`, `0-2`, `3-1`, `1-3`, minuta `70-88`, cena `0.60-0.99`.

Przyklad blokowany:

- `1-0`, `2-1`, `1-1`, brak score, strona `Yes`.

## Match Winner / Proof Of Winning

Rynek typu:

`Will Team A win on YYYY-MM-DD?`

Moze dotyczyc strony `Yes` albo `No`, ale tylko gdy score logicznie wspiera dany wybor:

- Dla `Yes`: wybrana druzyna musi prowadzic minimum `2` golami.
- Dla `No`: wybrana druzyna musi przegrywac minimum `2` golami.
- Jesli mecz jest na remisie, wejscie jest blokowane.
- Jesli wejscie wymagaloby comebacku lub przyszlego zdarzenia, jest blokowane.

Dodatkowy runtime `proof_of_winning` dziala w V2 i ma dwie sciezki:

- `stats_lite`: uzywa statystyk, ktore realnie wystepuja w Football API.
- `score_events`: bezpieczny fallback bez statystyk, oparty o score i eventy.

Wymagane:

- Fixture ID musi byc znaleziony.
- Musi istniec historia detail z Football API.
- Minuta `70-88`.
- Roznica goli minimum `2`.
- Lider nie moze miec czerwonej kartki.
- Brak gola w ostatnich `5` minutach.
- Brak czerwonej kartki w ostatnich `10` minutach.
- Warunek musi byc stabilny przez minimum `2` snapshoty.

### Proof stats-lite

Wymagane:

- Cena minimum `0.85`.
- Dane musza miec confidence flag.
- Musza byc obecne pola minimum:
  - `shots_last_5`,
  - `shots_last_10`,
  - `shots_on_target_last_10`,
  - `corners_last_10`.
- `Dangerous Attacks` i `Attacks` nie sa juz wymagane.

Jesli sa dostepne, system dodatkowo uzywa:

- `expected_goals`,
- `Shots insidebox`,
- `Blocked Shots`,
- `Yellow Cards`,
- `Ball Possession`.

Blokady presji / chaosu:

- Strzaly przegrywajacej strony w ostatnich 10 min `>= 4`.
- Celne strzaly przegrywajacej strony w ostatnich 10 min `>= 2`.
- Rogi przegrywajacej strony w ostatnich 10 min `>= 3`.
- Dangerous attacks przegrywajacej strony w ostatnich 10 min `>= 8`, jesli pole istnieje.
- xG przegrywajacej strony w ostatnich 10 min `>= 0.35`, jesli pole istnieje.
- Strzaly z pola karnego przegrywajacej strony w ostatnich 10 min `>= 3`, jesli pole istnieje.
- Trend presji `up`.
- Trend strzalow `up`.
- Trend dangerous attacks `up`.
- Gol w ostatnich `5` minutach.
- Czerwona kartka w ostatnich `10` minutach.
- Tempo change `up`.
- Brak stabilnosci przez minimum `2` snapshoty.

Wejscie koncowe ma reason:

`proof_of_winning_enter`

### Proof score-events

Fallback bez statystyk. Uzywany tylko, gdy `stats_lite` nie wejdzie, ale mamy historie eventow/score.

Wymagane:

- Cena minimum `0.90`.
- Minuta minimum `75` i `< 89`.
- Roznica goli minimum `2`.
- Lider nie ma czerwonej kartki.
- Brak czerwonej kartki w ostatnich `10` minutach.
- Brak gola w ostatnich `5` minutach.
- Warunek score/event musi byc stabilny przez minimum `2` snapshoty.

Wejscie koncowe ma reason:

`proof_of_winning_score_events_enter`

## Under Goals V2

Rynek typu:

`Team A vs. Team B: O/U X.5`

Gramy tylko strone `Under`.

Tryb aktywny:

- `score_only_v2_enabled: true`.
- Wejscie nie wymaga live statystyk typu `shots`, `attacks`, `dangerous_attacks`, `corners`.
- Statystyki live moga byc zapisane w diagnostyce, ale brak tych statystyk nie blokuje wejscia.

Warunki bazowe:

- Musi przejsc globalne filtry.
- Dodatkowo cena `Under` musi byc `>= 0.60`.
- Market musi byc poprawnie rozpoznany jako totals `O/U`.
- Strona musi byc dokladnie `Under`.
- Minuta `70-88`.
- Score musi byc znany.
- `goal_buffer = linia totalu - aktualna liczba goli`.
- Nie moze byc czerwonej kartki ani czerwonej kartki w ostatnich `10` minutach.
- Clock rynku musi byc wiarygodny: drift wzgledem start time nie moze przekraczac `12` minut.
- Fixture ID musi byc znaleziony.
- Musi istniec historia detail z Football API, ale wystarczy score/event history.
- Warunki score-only musza byc stabilne przez minimum `2` snapshoty.

Wymagany bufor:

- Minuta `70-74`: `goal_buffer >= 2.0`.
- Minuta `75-85`: `goal_buffer >= 1.0`.
- Minuta `86-88`: `goal_buffer >= 1.0`.

Blokady:

- Gol w ostatnich `3` lub `5` minutach.
- Czerwona kartka w meczu albo czerwona kartka w ostatnich `10` minutach.
- Brak stabilnosci przez minimum `2` snapshoty.
- Brak fixture ID.
- Brak historii detail/eventow potrzebnej do potwierdzenia stabilnosci.

Wejscie koncowe ma reason:

`goal_totals_under_v2_enter`

## Spread Confirmation V2

Rynek typu:

`Spread: Team A (-1.5)` albo odpowiedniki z plusem.

Tryb aktywny:

- `score_only_v2_enabled: true`.
- Wejscie nie wymaga live statystyk typu `shots`, `corners`, `attacks`, `dangerous_attacks`.
- Statystyki live moga byc zapisane w diagnostyce, ale brak tych statystyk nie blokuje wejscia.
- V2 jest konserwatywne: wymaga minimum `1` gola bufora ponad handicap.

### Spread Plus

Gramy selected side z handicapem dodatnim:

`+1.5`, `+2.5`, `+3.5`, `+4.5`

Warunki:

- Minuta `70-88`.
- Spread market musi byc poprawnie sparsowany.
- Selected side musi byc strona `plus`.
- Linia musi byc jedna z `+1.5`, `+2.5`, `+3.5`, `+4.5`.
- Score musi byc znany.
- Fixture ID musi byc znaleziony.
- Musi istniec historia detail z Football API, ale wystarczy score/event history.
- Warunki score-only musza byc stabilne przez minimum `2` snapshoty.

Wymagany bufor:

- `+1.5`: wybrana druzyna nie moze przegrywac, czyli margin `>= 0`.
- `+2.5`: wybrana druzyna moze przegrywac max `1` golem, czyli margin `>= -1`.
- `+3.5`: wybrana druzyna moze przegrywac max `2` golami, czyli margin `>= -2`.
- `+4.5`: wybrana druzyna moze przegrywac max `3` golami, czyli margin `>= -3`.

Blokady:

- Gol w ostatnich `3` lub `5` minutach.
- Czerwona kartka w meczu albo czerwona kartka w ostatnich `10` minutach.
- Brak stabilnosci przez minimum `2` snapshoty.

Wejscie koncowe ma reason:

`spread_plus_v2_enter`

### Spread Minus

Gramy selected side z handicapem ujemnym:

`-1.5`, `-2.5`, `-3.5`, `-4.5`

Warunki:

- Minuta `70-88`.
- Spread market musi byc poprawnie sparsowany.
- Selected side musi byc strona `minus`.
- Linia musi byc jedna z `-1.5`, `-2.5`, `-3.5`, `-4.5`.
- Score musi byc znany.
- Fixture ID musi byc znaleziony.
- Musi istniec historia detail z Football API, ale wystarczy score/event history.
- Warunki score-only musza byc stabilne przez minimum `2` snapshoty.

Wymagany bufor:

- `-1.5`: wybrana druzyna musi prowadzic minimum `3` golami.
- `-2.5`: wybrana druzyna musi prowadzic minimum `4` golami.
- `-3.5`: wybrana druzyna musi prowadzic minimum `5` golami.
- `-4.5`: wybrana druzyna musi prowadzic minimum `6` golami.

Blokady:

- Gol w ostatnich `3` lub `5` minutach.
- Czerwona kartka w meczu albo czerwona kartka w ostatnich `10` minutach.
- Brak stabilnosci przez minimum `2` snapshoty.

Wejscie koncowe ma reason:

`spread_minus_v2_enter`

## Price Hold

Samo `trade_eligible` nie wystarcza do wejscia.

Po przejsciu strategii cena musi jeszcze utrzymac sie przez `5s`. Dopiero wtedy entry reason dostaje suffix:

`price_held_Xs`

Przyklad:

`proof_of_winning_enter_price_held_5.2s`

## Kapital / stawka

Capital processes sa wlaczone.

- Start procesu: `10.0`.
- Target procesu: `21.0`.
- Max aktywnych procesow: `10`.
- Jesli proces jest gotowy, bot uzywa jego `current_balance` jako stake.
- Jesli wszystkie srodki sa w trade, config pozwala tworzyc nowy proces.

## Co obecnie nie jest objete statystykami

- `No Draw` nie ma osobnej analizy live statystyk.
- `No Draw` nie ma blokady po swiezym golu.
- `No Draw` nie ma filtra presji przegrywajacej druzyny.
- `Under Goals V2` celowo nie wymaga live statystyk.
- `Spread Confirmation V2` celowo nie wymaga live statystyk.
- Doliczony czas nie jest estymowany jako osobny warunek.
