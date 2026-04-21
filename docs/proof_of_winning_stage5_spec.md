# Proof Of Winning Stage 5 Spec

Etap 5 dodaje warstwe `effective_goal_difference` jako wersje v2 oceny jakosci przewagi.

## Cel etapu

Nie traktowac kazdego wyniku `2:0` lub `3:1` tak samo.

Zamiast tego liczyc:
- jakiej jakosci sa gole lidera
- czy przewaga jest zbudowana stabilnie
- czy dwa gole w poznej fazie rzeczywiscie "zabily mecz"

## Co zostalo wdrozone

Plik:
- `app/strategy/proof_of_winning_effective_lead.py`

Nowe elementy:
- `GoalEvent`
- `EffectiveGoalDifferenceResult`
- `effective_goal_difference_from_detail(detail_payload)`
- `populate_input_with_effective_goal_difference(base, result)`

## Aktualna logika wag

### Waga zależna od minuty

- `0-30` -> `0.8`
- `31-74` -> `1.0`
- `75+` -> `1.15`

### Waga karnego

- penalty goal -> mnoznik `0.7`
- normal goal -> mnoznik `1.0`

### Dwa gole w krotkim czasie

Jesli kolejny gol tej samej druzyny wpada w `<= 5 minut`:

- przed `30` minuta -> mnoznik `0.6`
- od `75` minuty -> mnoznik `1.05`

## Wynik

Liczony jest:

- `leader_weight_sum`
- `trailing_weight_sum`
- `effective_goal_difference = leader_weight_sum - trailing_weight_sum`

## Interpretacja robocza

- `>= 2.0` -> przewaga bardzo stabilna
- `1.8 - 1.99` -> przewaga akceptowalna
- `< 1.8` -> przewaga potencjalnie falszywa

## Ważna uwaga

Na tym etapie:
- `effective_goal_difference` jest juz liczony
- mozna go logowac i debugowac
- ale nie jest jeszcze obowiazkowym hard filtrem live wejscia

To celowo, bo wymaga kalibracji na realnych danych.

## Wejscie do kalkulatora

Kalkulator korzysta z:
- `fixture.goals`
- `fixture.teams`
- `events`

Czyli potrzebuje timeline goli z API-FOOTBALL.

## Co jeszcze nie jest zrobione

- brak osobnego reason code dla `effective_goal_difference < threshold`
- brak podpiecia tego do `enter_decision_v1`
- brak kalibracji wag na danych historycznych

To bedzie pozniej jako:
- `proof_of_winning_v2`

## Testy

Plik:
- `tests/test_proof_of_winning_effective_lead.py`

Pokryte:
- wczesny gol z karnego ma nizsza wage
- dwa pozne gole lidera podnosza efektywna przewage
- wynik mozna wstrzyknac do `ProofOfWinningInput`
