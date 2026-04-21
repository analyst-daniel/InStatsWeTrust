# Goal Totals Under Plan

Plan wdrozenia strategii `goal_totals_under` dla rynkow over/under w pilce noznej.

## Cel

Strategia ma oceniac tylko sytuacje typu:

- `Under 2.5`
- `Under 3.5`
- `Under 4.5`
- w dalszym kroku ewentualnie wyzsze linie `Under`

Strategia ma zwracac tylko:

- `ENTER`
- `NO ENTER`

W tej strategii:

- gramy tylko `UNDER`
- nie gramy `OVER`

## Glowna zasada

Under nie ma przewidywac gola.

Under ma odpowiadac na pytanie:

> czy mecz ofensywnie wygasa i czy do konca jest wystarczajaco malo czasu oraz za malo presji, zeby padl kolejny gol

Czyli gramy na:

- brak presji
- brak sytuacji
- brak chaosu
- spadajace tempo

## Twarde zasady startowe

- sport: tylko `soccer`
- aktywacja strategii: `minute >= 70`
- preferowane wejscia: `75 <= minute < 89`
- nie gramy w doliczonym czasie
- nie gramy `OVER`
- bez wiarygodnych danych live: `NO ENTER`
- jesli bufor gola jest za maly: `NO ENTER`
- nie wchodzimy po jednym snapshotcie
- decyzja strategii ma byc tylko:
  - `ENTER`
  - `NO ENTER`

## Core logic: goal buffer

Definicja:

- `goal_buffer = total_line - total_goals`

Przyklady:

- wynik `1:0`, `Under 2.5` -> buffer `1.5`
- wynik `2:0`, `Under 3.5` -> buffer `1.5`
- wynik `3:0`, `Under 4.5` -> buffer `1.5`

Zasady:

- `goal_buffer < 1.0` -> automatycznie `NO ENTER`
- `1.0 <= goal_buffer < 2.0` -> tylko przy bardzo spokojnym meczu
- `goal_buffer >= 2.0` -> standardowy lepszy setup

## Time factor

### 70-74
- strategia aktywna
- potrzebuje bardzo spokojnych statystyk
- preferowany buffer `>= 2`

### 75-85
- glowny zakres roboczy
- buffer `1-2` moze byc OK

### 86-88
- najlepszy moment
- buffer `>= 1` moze wystarczyc
- tylko jesli brak presji i brak chaosu

## Kluczowe live statystyki pod Under

### Brak strzalow
- shots_last_10
- shots_on_target_last_10

### Brak jakosci
- dangerous_attacks_last_10
- attacks_last_10

### Brak stalych fragmentow
- corners_last_10

### Brak stalej presji
- pressure_trend_last_10

### Spowolnienie gry
- tempo_change_last_10

### Chaos flags
- total_shots_both_last_10
- total_dangerous_attacks_both_last_10
- total_corners_both_last_10
- goal_in_last_3min
- goal_in_last_5min
- red_card_in_last_10min

## Zielone sygnaly

- shots_last_10 niskie
- shots_on_target_last_10 = 0
- dangerous attacks niskie
- corners niskie
- pressure trend flat albo down
- tempo stable albo down
- brak swiezego gola
- brak czerwonej kartki
- warunki stabilne przez 2-3 snapshoty

## Czerwone sygnaly

- 4+ strzaly w ostatnich 10 minutach
- 2+ celne strzaly
- seria rogow
- rosnacy pressure trend
- goal_in_last_3min = TRUE
- goal_in_last_5min = TRUE
- tempo rośnie
- czerwona kartka
- mecz otwarty i chaotyczny

## Etap 1 - Specyfikacja wejsc i parser totals market

Cel:
- zamknac definicje inputu i rozpoznawania rynku totals z Polymarket

Zakres:
- zdefiniowac input model strategii
- rozpoznac z `question`:
  - czy rynek jest totals
  - jaka jest linia totals
  - czy grana strona to `Under` czy `Over`
- strategia ma aktywowac sie tylko dla `Under`

Wejscia bazowe:
- minute
- score
- total_goals
- total_line
- goal_buffer
- side_type
- data_confidence_flag
- red_card_flag

Wynik etapu:
- parser poprawnie rozpoznaje `Under 2.5 / 3.5 / 4.5`
- `Over` jest odrzucany

## Etap 2 - Warstwa surowych danych meczowych

Cel:
- pobierac i zapisywac dane potrzebne do logiki under

Zakres:
- fixtures live
- fixtures statistics
- fixtures events
- parsed totals metadata w snapshotcie

Do zapisania lokalnie:
- surowy snapshot statystyk meczu
- surowy timeline zdarzen
- timestamp pobrania
- source freshness
- confidence flag
- parsed totals metadata

Wynik etapu:
- mamy lokalne dane do rolling metrics i debugu totals

## Etap 3 - Rolling metrics 5m / 10m dla UNDER

Cel:
- zbudowac dynamiczne metryki pod brak gola

Metryki:
- shots_last_5
- shots_on_target_last_5
- shots_last_10
- shots_on_target_last_10
- dangerous_attacks_last_5
- dangerous_attacks_last_10
- attacks_last_5
- attacks_last_10
- corners_last_5
- corners_last_10

Metryki chaosu:
- total_shots_both_last_10
- total_dangerous_attacks_both_last_10
- total_corners_both_last_10
- goal_in_last_3min
- goal_in_last_5min
- red_card_in_last_10min
- tempo_change_last_10

Metryki trendu:
- pressure_trend_last_10
- shots_trend_last_10
- dangerous_attacks_trend_last_10

Dodatkowe pola:
- time_since_last_goal
- stable_for_2_snapshots
- stable_for_3_snapshots

Wynik etapu:
- strategia ma rolling context zamiast patrzec na cale meczowe sumy

## Etap 4 - Under Activation Rules

Cel:
- zbudowac twarde warunki aktywacji

Warunki:
- `minute >= 70`
- `minute < 89`
- `data_confidence_flag = TRUE`
- strona rynku = `Under`
- `goal_buffer >= 1.0`
- brak czerwonej kartki

Dodatkowy podzial:
- `70-74` -> bardziej restrykcyjny tryb
- `75-85` -> standard
- `86-88` -> relaxed but still safe

Wynik etapu:
- rynek totals trafia do dalszej logiki tylko gdy jest sens analizowac `Under`

## Etap 5 - Under Enter Decision V1

Cel:
- wdrozyc pierwsza wersje decyzji `ENTER / NO ENTER`

Warunki ENTER v1:
- buffer `>= 1.0`
- shots_last_10 niskie
- shots_on_target_last_10 bardzo niskie
- corners_last_10 niskie
- dangerous_attacks_last_10 niskie
- pressure trend nie rośnie
- tempo nie rośnie
- brak swiezego gola
- brak chaosu
- stabilnosc przez 2-3 snapshoty

Zasada dodatkowa:
- dla buforu `1.x` progi bardziej ostre
- dla buforu `2.x+` progi standardowe

Wynik etapu:
- pierwsza wersja `under_enter_v1`

## Etap 6 - Integracja ze strategia paper trading

Cel:
- podlaczyc `goal_totals_under` jako osobna logike wejscia

Zakres:
- osobna sciezka dla totals
- osobne reason codes
- osobne logowanie do snapshotow i trade log
- blokowanie `Over`

Przyklad reason codes:
- `goal_totals_under_enter`
- `goal_totals_under_wrong_side`
- `goal_totals_under_buffer_too_small`
- `goal_totals_under_no_enter_pressure`
- `goal_totals_under_no_enter_chaos`
- `goal_totals_under_no_enter_recent_goal`
- `goal_totals_under_no_enter_not_stable`

Wynik etapu:
- totals market nie wejdzie bez przejscia przez logike under

## Etap 7 - Dashboard i debug

Cel:
- pokazac, dlaczego under wszedl albo nie wszedl

Do pokazania w dashboardzie:
- minute
- score
- total_line
- total_goals
- goal_buffer
- shots_last_10
- shots_on_target_last_10
- corners_last_10
- dangerous_attacks_last_10
- pressure trend
- chaos flags
- stability flags
- final decision
- rejection reason

Wynik etapu:
- mozna debugowac case under bez zgadywania

## Etap 8 - Testy i kalibracja

Cel:
- sprawdzic czy progi dla under maja sens na realnych danych

Testy:
- test parsera totals line
- test odrzucenia `Over`
- test odrzucenia przy `goal_buffer < 1`
- test odrzucenia przy czerwonej kartce
- test odrzucenia przy wysokiej presji
- test odrzucenia przy chaosie
- test odrzucenia po swiezym golu
- test wymogu `2-3` stabilnych snapshotow
- test braku wejsc przy missing data

Kalibracja:
- porownanie wygranych i przegranych
- analiza po lidze
- analiza po minucie wejscia
- analiza po linii:
  - `Under 2.5`
  - `Under 3.5`
  - `Under 4.5`
  - pozniej kolejne

## Docelowa zasada decyzyjna

### ENTER tylko gdy:

- rynek to `Under`
- minute `>= 70` i `< 89`
- `goal_buffer >= 1`
- brak czerwonej kartki
- brak presji
- brak chaosu
- trend nie rośnie
- warunki utrzymane przez `2-3 snapshoty`

### NO ENTER gdy:

- to `Over`
- buffer za maly
- swiezy gol
- rosnaca presja
- chaos
- czerwona kartka
- brak stabilnosci
- brak danych

## Uwagi robocze

- na start nie wdrazamy `Over`
- na start nie dajemy possession i substitutions do twardej decyzji
- te pola mozna zbierac do debug i kalibracji, ale nie musza od razu blokowac wejscia
- najwazniejsze sa ostatnie `5-10 minut`, nie statystyki calego meczu
- najpierw robimy `Under 2.5 / 3.5 / 4.5`
- wyzsze linie dopiero po zebraniu danych
