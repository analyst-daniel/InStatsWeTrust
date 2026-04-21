# Proof Of Winning Stage 1 Spec

Etap 1 zamyka definicje danych wejsciowych i warunku aktywacji strategii.

## Cel etapu

Zbudowac jeden stabilny model wejscia dla strategii `proof_of_winning`, zanim zaczniemy pobierac dodatkowe statystyki i liczyc rolling metrics.

## Co uznajemy za gotowe po Etapie 1

- istnieje jeden input model strategii
- sa zdefiniowane pola wymagane i opcjonalne
- jest osobna funkcja aktywacji strategii
- strategia nie uruchamia sie poza oknem `75 <= minute < 89`
- strategia nie uruchamia sie bez przewagi `2+`
- strategia nie uruchamia sie przy czerwonej kartce lidera
- strategia nie uruchamia sie bez minimalnego zestawu danych

## Input model

Model:
- `ProofOfWinningInput`

Plik:
- `app/strategy/proof_of_winning.py`

### Pola bazowe

- `event_id`
- `event_slug`
- `event_title`
- `market_id`
- `market_slug`
- `question`
- `side`
- `minute`
- `score`
- `goal_difference`
- `leader_team`
- `trailing_team`
- `leader_red_card`
- `trailing_red_card`
- `data_confidence_flag`

### Rolling metrics placeholder

Na Etapie 1 pola juz istnieja w modelu, ale beda zasilane dopiero w kolejnych etapach:

- `shots_last_5`
- `shots_on_target_last_5`
- `shots_last_10`
- `shots_on_target_last_10`
- `dangerous_attacks_last_5`
- `dangerous_attacks_last_10`
- `corners_last_5`
- `corners_last_10`
- `total_shots_both_last_10`
- `total_dangerous_attacks_both_last_10`
- `total_corners_both_last_10`
- `goal_in_last_3min`
- `goal_in_last_5min`
- `red_card_in_last_10min`
- `pressure_trend_last_10`
- `shots_trend_last_10`
- `dangerous_attacks_trend_last_10`
- `tempo_change_last_10`
- `stable_for_2_snapshots`
- `stable_for_3_snapshots`

### Metadata o jakosci danych

- `source_fields_present`

To pole mowi, ktore wymagane metryki sa rzeczywiscie dostepne dla danej decyzji.

## Time bucket

Na Etapie 1 wprowadzamy bucket czasu:

- `75_80`
- `81_85`
- `86_88`
- `outside`

Nie gramy:
- przed 75 minuta
- od 89 minuty wzwyz
- w doliczonym czasie

## Minimalny warunek aktywacji

Strategia moze przejsc do dalszej analizy tylko gdy:

- `minute >= 75`
- `minute < 89`
- `goal_difference >= 2`
- `leader_red_card = FALSE`
- `data_confidence_flag = TRUE`
- sa dostepne pola:
  - `shots_last_5`
  - `shots_last_10`
  - `shots_on_target_last_10`
  - `dangerous_attacks_last_10`
  - `corners_last_10`

## Activation reason codes

Na Etapie 1 aktywacja zwraca jeden z powodow:

- `proof_of_winning_activation_ok`
- `proof_of_winning_minute_outside_window`
- `proof_of_winning_goal_difference_too_low`
- `proof_of_winning_leader_red_card`
- `proof_of_winning_low_data_confidence`
- `proof_of_winning_missing_required_fields`

## Testy Etapu 1

Testujemy:

- poprawna aktywacja dla poprawnego inputu
- odrzucenie od `89.0`
- odrzucenie przy przewadze `< 2`
- odrzucenie przy czerwonej kartce lidera
- odrzucenie przy brakujacych wymaganych polach

Plik testow:
- `tests/test_proof_of_winning.py`

## Co dalej w Etapie 2

Po zamknieciu Etapu 1 przechodzimy do pobierania surowych danych:

- Football API live fixtures
- Football API statistics
- Football API events

I dopiero potem budujemy rolling metrics dla strategii.
