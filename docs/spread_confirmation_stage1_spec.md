## Etap 1 - Specyfikacja wejsc i parser spreadu

Cel etapu:

- zamknac model wejscia dla strategii `spread_confirmation`,
- poprawnie parsowac rynek `Spread: Team (+/-line)`,
- rozroznic:
  - linie wystawiona w pytaniu,
  - strone faktycznie grana przez nasz `side`.

Zakres:

1. Input model strategii:
   - `SpreadConfirmationInput`
   - pola bazowe:
     - `minute`
     - `score`
     - `home_team`
     - `away_team`
     - `home_goals`
     - `away_goals`
     - `goal_difference`
     - `leader_team`
     - `trailing_team`
     - `spread_team`
     - `spread_line`
     - `spread_side_type`
     - `selected_team`
     - `selected_line`
     - `selected_side_type`
     - `data_confidence_flag`
     - `leader_red_card`
     - `trailing_red_card`

2. Parser rynku:
   - wejscie:
     - `question`
     - `side`
   - przyklad:
     - `question = Spread: Iwaki FC (-2.5)`
     - `side = Iwaki FC`
       - `selected_line = -2.5`
       - `selected_side_type = minus`
     - `side = AC Nagano Parceiro`
       - `selected_line = +2.5`
       - `selected_side_type = plus`

3. Kluczowa zasada:
   - parser musi rozrozniac to, co jest wystawione w `question`, od tego co faktycznie gramy przez `side`
   - ta roznica jest krytyczna dla dalszej logiki `spread_plus` i `spread_minus`

4. Warunek poprawnosci parsera:
   - jesli nie da sie sparsowac pytania spreadu:
     - `valid = False`
     - strategia nie moze przejsc dalej

5. Time buckets:
   - `75-80`
   - `81-85`
   - `86-88`
   - `outside`

6. Wynik etapu:
   - mamy stabilny model wejscia i parser linii handicapu
   - mozemy bezpiecznie wejsc w Etap 2 i Etap 4/5
