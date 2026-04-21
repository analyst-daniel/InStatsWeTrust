# Proof Of Winning Stage 2 Spec

Etap 2 dodaje surowe dane z API-FOOTBALL potrzebne do dalszych metryk strategii.

## Cel etapu

Miec lokalnie zapisane:

- `fixtures live`
- `fixture statistics`
- `fixture events`

dla wybranych meczow live soccer, tak zeby Etap 3 mogl liczyc rolling metrics bez zgadywania.

## Co zostalo wdrozone

### 1. Rozszerzenie klienta API-FOOTBALL

Plik:
- `app/live_state/football_api_client.py`

Nowe metody:
- `fixture_statistics(fixture_id)`
- `fixture_events(fixture_id)`

### 2. Research store dla surowych danych

Plik:
- `app/live_state/football_research.py`

Zadania:
- zapis `fixtures_live_latest.json`
- zapis szczegolow per fixture do:
  - `latest.json`
- manifest odswiezen:
  - `football_research_manifest.json`

### 3. Integracja z football fallback

Plik:
- `app/live_state/football_fallback.py`

Po kazdym pobraniu `fixtures?live=all`:
- aktualizowany jest live state cache
- zapisywany jest surowy `fixtures_live_latest.json`
- dla wybranych fixture pobierane sa:
  - statistics
  - events

### 4. Integracja z runnerem

Plik:
- `scripts/run_football_fallback.py`

Nowy output:
- `captured=<n>`

To pokazuje, dla ilu fixture w danym cyklu pobrano szczegoly do strategii.

## Zasady capture szczegolow

Szczegoly sa pobierane tylko gdy:

- fixture jest live
- fixture jest soccer / football
- `elapsed >= detail_capture_minute_floor`
- minelo co najmniej `detail_capture_poll_interval_seconds` od ostatniego fetchu dla tego fixture

## Konfiguracja

Plik:
- `config/settings.yaml`

Nowe pola:

- `storage.football_research_manifest_json`
- `football_api.detail_capture_enabled`
- `football_api.detail_capture_minute_floor`
- `football_api.detail_capture_poll_interval_seconds`

Aktualne domysly:

- `detail_capture_enabled: true`
- `detail_capture_minute_floor: 70`
- `detail_capture_poll_interval_seconds: 30`

## Gdzie zapisuja sie dane

### Manifest

- `data/snapshots/football_research_manifest.json`

### Raw fixtures live

- `data/raw/football_api/YYYY-MM-DD/fixtures_live_latest.json`

### Raw detail per fixture

- `data/raw/football_api/YYYY-MM-DD/<fixture_id>/latest.json`

## Co zawiera detail per fixture

- `fixture_id`
- `event_title`
- `fixture`
- `statistics`
- `events`
- `saved_at`

## Testy

Plik:
- `tests/test_football_research.py`

Pokryte:
- helpery fixture
- selekcja live soccer fixture
- guard odswiezania manifestu

## Co jeszcze nie jest zrobione

Etap 2 jeszcze nie liczy:

- shots last 5
- shots last 10
- corners last 10
- pressure trend
- chaos metrics

To bedzie Etap 3.
