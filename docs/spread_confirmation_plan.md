# Spread Confirmation Plan

Plan wdrozenia strategii `spread_confirmation` dla rynkow handicap / spread w pilce noznej.

## Cel

Strategia ma oceniac, czy konkretny spread ma sens w koncowce meczu, przy wykorzystaniu:

- aktualnego wyniku,
- realnego marginesu wzgledem linii handicapu,
- live score i minute,
- presji i aktywnosci obu druzyn z ostatnich 5-10 minut,
- trendu,
- chaosu meczu,
- stabilnosci sygnalu przez kolejne snapshoty.

## Podzial strategii

Strategia jest rozdzielona na dwa osobne tryby:

- `spread_minus`
  - np. `-1.5`, `-2.5`, `-3.5`
  - pytanie: czy lider utrzyma wymagany margines do konca

- `spread_plus`
  - np. `+1.5`, `+2.5`, `+3.5`
  - pytanie: czy underdog nie peknie i utrzyma handicap

To beda dwie osobne logiki wejscia, nawet jesli beda wspoldzielic te same dane live.

## Twarde zasady startowe

- sport: tylko `soccer`
- analiza aktywna tylko dla `75 <= minute < 89`
- nie gramy w doliczonym czasie
- brak wejsc bez wiarygodnych danych live
- nie opieramy decyzji tylko na samym wyniku
- nie wchodzimy po jednym snapshotcie
- dla spreadu ujemnego sprawdzenie aktualnego marginesu wzgledem linii jest twardym `pre-filter`
- jesli wynik nie pokrywa logicznie handicapu, to decyzja ma byc natychmiast `NO ENTER`
- decyzja strategii ma byc tylko:
  - `ENTER`
  - `NO ENTER`

## Etap 1 - Specyfikacja wejsc i parser spreadu

Cel:
- zamknac definicje inputu i rozpoznawania linii spreadu z rynku Polymarket

Zakres:
- zdefiniowac input model strategii
- rozdzielic:
  - `spread_side_type = minus`
  - `spread_side_type = plus`
- wyciagnac z `question`:
  - druzyne wystawiona przy spreadzie
  - linie handicapu
  - znak linii
- ustalic:
  - ktora druzyna jest liderem
  - ktora jest underdogiem
  - ktora strona rynku jest tak naprawde grana

Wejscia bazowe:
- minute
- score
- home_goals
- away_goals
- goal_difference
- leader_team
- trailing_team
- spread_team
- spread_line
- spread_side_type
- data_confidence_flag
- red_cards_home
- red_cards_away

Warunek aktywacji ogolny:
- `minute >= 75`
- `minute < 89`
- `data_confidence_flag = TRUE`
- poprawnie sparsowany spread

## Etap 2 - Warstwa surowych danych meczowych

Cel:
- pobierac i zapisywac dane potrzebne do logiki spreadu

Zakres:
- fixtures live
- fixtures statistics
- fixtures events
- dodatkowo zapis tego, jaka linia spreadu byla analizowana w snapshotcie

Do zapisania lokalnie:
- surowy snapshot statystyk meczu
- surowy timeline zdarzen
- timestamp pobrania
- source freshness
- confidence flag
- parsed spread metadata

Wynik etapu:
- mamy lokalne dane do obliczania rolling metrics dla obu stron handicapu

## Etap 3 - Rolling metrics 5m / 10m dla obu druzyn

Cel:
- zbudowac dynamiczne metryki nie tylko dla przegrywajacego, ale dla obu stron meczu

Metryki dla lidera:
- leader_shots_last_5
- leader_shots_on_target_last_5
- leader_shots_last_10
- leader_shots_on_target_last_10
- leader_dangerous_attacks_last_5
- leader_dangerous_attacks_last_10
- leader_corners_last_5
- leader_corners_last_10

Metryki dla underdoga / trailing team:
- underdog_shots_last_5
- underdog_shots_on_target_last_5
- underdog_shots_last_10
- underdog_shots_on_target_last_10
- underdog_dangerous_attacks_last_5
- underdog_dangerous_attacks_last_10
- underdog_corners_last_5
- underdog_corners_last_10

Metryki chaosu:
- total_shots_both_last_10
- total_dangerous_attacks_both_last_10
- total_corners_both_last_10
- goal_in_last_3min
- goal_in_last_5min
- red_card_in_last_10min
- tempo_change_last_10

Metryki trendu:
- leader_pressure_trend_last_10
- underdog_pressure_trend_last_10
- shots_trend_last_10
- dangerous_attacks_trend_last_10

Dodatkowe metryki pomocnicze:
- time_since_last_goal
- stable_for_2_snapshots
- stable_for_3_snapshots

Wynik etapu:
- strategia ma juz dane rolling dla obu druzyn zamiast tylko statystyk calomeczowych

## Etap 4 - Spread Plus V1

Cel:
- wdrozyc pierwsza wersje logiczna dla `+1.5` i `+2.5`

Główna zasada:
- nie pytamy, czy underdog wygra
- pytamy, czy nie przegra za wysoko

Startowy priorytet:
- najpierw `+1.5`
- potem `+2.5`
- rozszerzenie:
  - `+3.5`
  - `+4.5`

Warunki bazowe:
- `minute >= 75`
- `minute < 89`
- `data_confidence_flag = TRUE`
- brak czerwonej kartki dla druzyny z dodatnim spreadem

Logika dla `+1.5`:
- preferowany wynik:
  - remis
  - prowadzenie underdoga
  - przegrana tylko 1 golem
- underdog musi nadal zyc w meczu
- rywal nie moze generowac lawiny sytuacji

Logika dla `+2.5`:
- preferowany wynik:
  - remis
  - prowadzenie underdoga
  - przegrana 1 golem
  - ostroznie przegrana 2 golami tylko przy zywych stats

Warunki ENTER v1:
- underdog ma aktywnosc ofensywna
- underdog nie znika z meczu
- rywal nie dominuje calkowicie
- brak chaosu
- stabilnosc przez `2-3 snapshoty`

Wynik etapu:
- pierwsza dzialajaca decyzja `ENTER / NO ENTER` dla `spread_plus`

## Etap 5 - Spread Minus V1

Cel:
- wdrozyc pierwsza wersje logiczna dla `-1.5` i `-2.5`

Główna zasada:
- sam wynik nie wystarczy
- lider musi juz miec wymagany margines
- live stats musza potwierdzac, ze ten margines utrzyma

Startowy priorytet:
- najpierw `-1.5`
- potem `-2.5`
- rozszerzenie:
  - `-3.5`
  - `-4.5`

Twarde zasady:
- dla `-1.5`:
  - nie gramy przy `1:0`
  - minimum logiczne: `2 gole przewagi`
  - preferencyjnie: `3 gole przewagi`
- dla `-2.5`:
  - minimum logiczne: `3 gole przewagi`
  - preferencyjnie: `4 gole przewagi`
- dla `-3.5`:
  - minimum logiczne: `4 gole przewagi`
  - preferencyjnie: `5 goli przewagi`
- dla `-4.5`:
  - minimum logiczne: `5 goli przewagi`
  - preferencyjnie: `6 goli przewagi`

Hard pre-filter:
- najpierw sprawdzamy, czy aktualny wynik w ogole logicznie pokrywa linie
- jesli nie pokrywa:
  - nie analizujemy dalej presji
  - nie analizujemy trendu
  - nie analizujemy chaosu
  - decyzja jest od razu `NO ENTER`
- przyklad:
  - `-1.5` przy `1:0` -> `NO ENTER`
  - `-2.5` przy `1:0` -> `NO ENTER`
  - `-2.5` przy `2:0` -> dalej `NO ENTER`
  - `-2.5` przy `3:0` -> dopiero mozna przejsc do dalszej analizy live stats
  - `-3.5` przy `3:0` -> `NO ENTER`
  - `-3.5` przy `4:0` -> dopiero mozna przejsc do dalszej analizy live stats
  - `-4.5` przy `4:0` -> `NO ENTER`
  - `-4.5` przy `5:0` -> dopiero mozna przejsc do dalszej analizy live stats

Warunki ENTER v1:
- `minute >= 75`
- `minute < 89`
- `data_confidence_flag = TRUE`
- brak czerwonej kartki dla lidera
- aktualny margines juz pokrywa spread
- lider nadal kontroluje mecz
- przegrywajacy nie naciska mocno
- brak chaosu
- stabilnosc przez `2-3 snapshoty`

Wynik etapu:
- pierwsza dzialajaca decyzja `ENTER / NO ENTER` dla `spread_minus`

## Etap 6 - Integracja ze strategia paper trading

Cel:
- podlaczyc `spread_confirmation` jako osobna logike wejscia

Zakres:
- osobna sciezka walidacji dla plus/minus spread
- osobne reason codes
- osobne logowanie do snapshotow i trade log
- mozliwosc porownania z innymi strategiami

Przyklad reason codes:
- `spread_plus_enter`
- `spread_plus_no_enter_pressure`
- `spread_plus_no_enter_red_card`
- `spread_plus_no_enter_not_stable`
- `spread_minus_enter`
- `spread_minus_no_enter_margin_too_small`
- `spread_minus_no_enter_pressure`
- `spread_minus_no_enter_chaos`
- `spread_minus_no_enter_not_stable`

## Etap 7 - Dashboard i debug

Cel:
- pokazac dlaczego spread wszedl albo nie wszedl

Do pokazania w dashboardzie:
- minute
- score
- spread_line
- spread_side_type
- aktualny margines goli
- leader stats last 10
- underdog stats last 10
- pressure trends
- chaos flags
- stability flags
- final decision
- rejection reason

Wynik etapu:
- mozna debugowac case spreadu bez zgadywania

## Etap 8 - Testy i kalibracja

Cel:
- sprawdzic czy progi maja sens na realnych danych

Testy:
- test aktywacji tylko dla `75 <= minute < 89`
- test parsera spread line
- test odrzucenia `-1.5` przy `1:0`
- test odrzucenia przy zbyt malym marginesie
- test odrzucenia przy czerwonej kartce
- test odrzucenia przy wysokiej presji
- test odrzucenia przy chaosie
- test wymogu `2-3` stabilnych snapshotow
- test braku wejsc przy missing data

Kalibracja:
- porownanie wygranych i przegranych
- analiza po lidze
- analiza po minucie wejscia
- analiza po typie spreadu
- analiza po linii:
  - `+1.5`
  - `-1.5`
  - `+2.5`
  - `-2.5`
  - `+3.5`
  - `-3.5`
  - `+4.5`
  - `-4.5`

## Docelowa zasada decyzyjna

### Spread Plus

ENTER tylko gdy:

- `minute >= 75`
- `minute < 89`
- wynik nadal miesci sie logicznie w handicapie
- underdog nadal zyje w meczu
- rywal nie dominuje calkowicie
- brak chaosu
- warunki utrzymaly sie przez `2-3 snapshoty`

NO ENTER:

- wszystko inne

### Spread Minus

ENTER tylko gdy:

- `minute >= 75`
- `minute < 89`
- lider juz ma wymagany margines dla linii
- lider nie oddal kontroli
- przegrywajacy nie naciska mocno
- brak chaosu
- warunki utrzymaly sie przez `2-3 snapshoty`

NO ENTER:

- wszystko inne

## Uwagi robocze

- nie wdrazamy wszystkiego naraz
- najpierw robimy:
  - `+1.5`
  - `-1.5`
- potem:
  - `+2.5`
  - `-2.5`
- rozszerzenie:
  - `+3.5`
  - `-3.5`
  - `+4.5`
  - `-4.5`
- spread minus jest bardziej zdradliwy niz spread plus
- najwazniejsze sa ostatnie `5-10 minut`, nie caly mecz
- trend i chaos sa wazniejsze niz pojedynczy odczyt
