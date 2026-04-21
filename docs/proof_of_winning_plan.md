# Proof Of Winning Plan

Plan wdrozenia strategii `proof_of_winning` dla rynku typu "czy druzyna dowiezie zwyciestwo".

## Cel

Strategia ma oceniac, czy druzyna prowadzaca w koncowce meczu dowiezie zwyciestwo, przy wykorzystaniu:

- live score i minute,
- presji druzyny przegrywajacej,
- trendu z ostatnich 5-10 minut,
- filtrow chaosu,
- stabilnosci sygnalu przez kolejne snapshoty.

## Twarde zasady startowe

- sport: tylko soccer
- analiza aktywna tylko dla `75 <= minute < 89`
- nie gramy w doliczonym czasie
- przewaga lidera musi wynosic minimum `2 gole`
- brak czerwonej kartki dla lidera
- brak wejscia bez wiarygodnych danych live
- decyzja strategii ma byc tylko:
  - `ENTER`
  - `NO ENTER`

## Etap 1 - Specyfikacja wejsc i danych

Cel:
- zamknac definicje danych wejsciowych i pol pochodnych

Zakres:
- zdefiniowac input model dla strategii
- ustalic, ktore pola bierzemy z:
  - Football API live fixtures
  - Football API statistics
  - Football API events timeline
  - Polymarket live state / snapshots
- ustalic minimalny zestaw danych obowiazkowych

Wejscia bazowe:
- minute
- score
- goal_difference
- leader_team
- trailing_team
- leader_red_card
- trailing_red_card
- time_bucket:
  - 75-80
  - 81-85
  - 86-88
- data_confidence_flag

Warunek aktywacji strategii:
- `minute >= 75`
- `minute < 89`
- `goal_difference >= 2`
- `leader_red_card = FALSE`
- `data_confidence_flag = TRUE`

## Etap 2 - Warstwa surowych danych meczowych

Cel:
- pobierac i zapisywac dane potrzebne do logiki

Zakres:
- fixtures live
- fixtures statistics
- fixtures events

Do zapisania lokalnie:
- surowy snapshot statystyk meczu
- surowy timeline zdarzen
- timestamp pobrania
- source freshness
- confidence flag

Wynik etapu:
- mamy lokalne dane do obliczania rolling metrics

## Etap 3 - Rolling metrics 5m / 10m

Cel:
- zbudowac metryki dynamiczne z ostatnich 5 i 10 minut

Metryki dla druzyny przegrywajacej:
- shots_last_5
- shots_on_target_last_5
- shots_last_10
- shots_on_target_last_10
- dangerous_attacks_last_5
- dangerous_attacks_last_10
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

Dodatkowe metryki pomocnicze:
- time_since_last_goal
- time_since_last_shot
- stable_for_2_snapshots
- stable_for_3_snapshots

Wynik etapu:
- strategia ma juz dane rolling zamiast tylko statystyk calomeczowych

## Etap 4 - V1 hard filters

Cel:
- wdrozyc pierwsza wersje logiczna bez skomplikowanego scoringu

Warunki obowiazkowe:
- `minute >= 75`
- `minute < 89`
- `goal_difference >= 2`
- `leader_red_card = FALSE`
- `data_confidence_flag = TRUE`
- dostepne dane:
  - `shots_last_5`
  - `shots_last_10`
  - `shots_on_target_last_10`
  - `dangerous_attacks_last_10`
  - `corners_last_10`

Filtr presji druzyny przegrywajacej:
- ENTER tylko gdy:
  - `shots_last_10 <= 2`
  - `shots_on_target_last_10 == 0`
  - `corners_last_10 <= 1`
  - `dangerous_attacks_last_10` niski

Automatyczny NO ENTER gdy:
- `shots_last_10 >= 4`
- `shots_on_target_last_10 >= 2`
- `corners_last_10 >= 3`
- `dangerous_attacks_last_10` wysoki

Filtr trendu:
- ENTER tylko gdy:
  - `pressure_trend_last_10 != up`
  - `shots_trend_last_10 != up`
  - `dangerous_attacks_trend_last_10 != up`

Filtr chaosu:
- ENTER tylko gdy:
  - `goal_in_last_3min = FALSE`
  - `red_card_in_last_10min = FALSE`
  - `tempo_change_last_10 != up`

Stability requirement:
- warunki musza byc utrzymane przez minimum `2-3 kolejne snapshoty`

Wynik etapu:
- pierwsza dzialajaca decyzja `ENTER / NO ENTER`

## Etap 5 - Effective goal difference v2

Cel:
- rozszerzyc surowe `goal_difference` o jakosc przewagi

Robocza definicja:
- `effective_goal_difference`

Potencjalne skladowe:
- minuta zdobycia gola
- typ gola:
  - open play
  - penalty
- odstep miedzy golami
- czy drugi gol "zabil mecz" czy tylko chwilowo podbil wynik

Interpretacja:
- `>= 1.8` -> przewaga wystarczajaco stabilna
- `< 1.8` -> przewaga potencjalnie falszywa

Uwaga:
- ten etap wdrazamy dopiero po zebraniu danych i kalibracji

## Etap 6 - Integracja ze strategia paper trading

Cel:
- podlaczyc `proof_of_winning` jako osobna logike wejscia

Zakres:
- osobny reason code dla wejsc
- osobna sciezka walidacji
- osobne logowanie do snapshotow i trade log
- mozliwosc rownoleglego porownania z obecna strategia

Reason codes:
- `proof_of_winning_enter`
- `proof_of_winning_no_enter_low_confidence`
- `proof_of_winning_no_enter_pressure`
- `proof_of_winning_no_enter_trend_up`
- `proof_of_winning_no_enter_chaos`
- `proof_of_winning_no_enter_not_stable`

## Etap 7 - Dashboard i debug

Cel:
- pokazac dlaczego strategia weszla lub nie weszla

Do pokazania w dashboardzie:
- minute
- score
- goal_difference
- shots_last_10
- shots_on_target_last_10
- corners_last_10
- dangerous_attacks_last_10
- pressure_trend_last_10
- tempo_change_last_10
- goal_in_last_3min
- red_card_in_last_10min
- stability flag
- final decision
- rejection reason

Wynik etapu:
- mozna debugowac wejscia bez zgadywania

## Etap 8 - Testy i kalibracja

Cel:
- sprawdzic czy progi sa sensowne na realnych danych

Testy:
- test aktywacji tylko dla `75 <= minute < 89`
- test odrzucenia przy czerwonej kartce lidera
- test odrzucenia przy wysokiej presji trailing team
- test odrzucenia przy chaosie
- test wymogu 2-3 stabilnych snapshotow
- test braku wejsc przy missing data

Kalibracja:
- porownanie wygranych i przegranych
- analiza po lidze
- analiza po minucie wejscia
- analiza po typie rynku
- analiza po poziomie presji i trendu

## Docelowa zasada decyzyjna

### ENTER tylko gdy:

- `minute >= 75`
- `minute < 89`
- `goal_difference >= 2`
- `leader_red_card = FALSE`
- `data_confidence_flag = TRUE`
- trailing team ma niska presje
- trend presji nie rosnie
- mecz nie jest w fazie chaosu
- warunki utrzymaly sie przez `2-3 snapshoty`

### NO ENTER:

- wszystko inne

## Uwagi robocze

- nie uzywamy extra time jako osobnego filtra, bo strategia konczy sie przed `89` minuta
- najwazniejsze sa ostatnie `5-10 minut`, nie caly mecz
- presja jest wazniejsza niz possession
- trend jest wazniejszy niz pojedynczy odczyt
- chaos jest czerwonym alarmem
- najpierw wdrazamy wersje `v1`, potem rozszerzenia `v2`
