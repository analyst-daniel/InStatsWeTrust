## Etap 7 - Dashboard i Debug

Cel etapu:

- pokazac na dashboardzie, dlaczego `proof_of_winning` daje `ENTER` albo `NO ENTER`,
- usunac zgadywanie przy analizie live i po sesji,
- miec debug oparty o aktualne snapshoty 0.95-0.99 oraz aktualny live state.

Zakres wdrozenia:

1. Nowa sekcja dashboardu:
   - `Proof Of Winning Debug`

2. Dane w sekcji debug:
   - `timestamp_utc`
   - `event_title`
   - `question`
   - `side`
   - `final_decision`
   - `rejection_reason`
   - `minute`
   - `score`
   - `goal_difference`
   - `effective_goal_difference`
   - `shots_last_10`
   - `shots_on_target_last_10`
   - `corners_last_10`
   - `dangerous_attacks_last_10`
   - `pressure_trend_last_10`
   - `tempo_change_last_10`
   - `goal_in_last_3min`
   - `red_card_in_last_10min`
   - `stable_for_2_snapshots`
   - `stable_for_3_snapshots`

3. Zasada budowy:
   - bierzemy aktualne `latest` snapshoty z dashboard payload,
   - mapujemy je do `NormalizedMarket`,
   - dopinamy aktualny `LiveState`,
   - odpalamy `ProofOfWinningRuntime.evaluate(...)`,
   - pokazujemy tylko markety, dla ktorych strategia ma zastosowanie.

4. Dodatkowe dopiecie:
   - `entry_reason` widoczny w open/resolved trades,
   - debug sekcja nie zmienia logiki tradingowej, tylko ja ujawnia.

Wynik etapu:

- dashboard pokazuje nie tylko sygnal, ale tez powod,
- mozna szybko sprawdzic:
  - czy blokada wynika z presji,
  - czy z trendu,
  - czy z chaosu,
  - czy z braku stabilnosci,
  - czy z braku danych / historii.
