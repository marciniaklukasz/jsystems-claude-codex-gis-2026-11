# Profil danych map-qa (krok 0b)

**Data:** 2026-11-03 · **Gałąź:** `worktree-map-qa-prototype` · **Baza:** `03dcb56`
**Zakres:** tylko odczyt plików w `course-materials/exercise-data/map-qa/`; wejścia niezmienione, brak pobrań zdjęć, brak wywołań modeli. Databricks i API nie były odpytywane (brak ustawionych zmiennych w tej sesji) — patrz „Ograniczenia”.

## Środowisko

| Element | Wersja |
|---|---|
| uv | 0.13.7 (winget) |
| Python | 3.12.16 (uv managed) |
| duckdb | 1.5.6 (z nagłówka `profile_data.py`) |
| geopandas / pyarrow | 1.2.0 / 23.0.1 (README danych) |
| Pillow | 12.0.0 (z nagłówka `download_photos.py`) |

Na Windows skrypty wypisujące tabele DuckDB wymagają `PYTHONIOENCODING=utf-8`; bez tego `UnicodeEncodeError` (konsola cp1250).

## Polecenia

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run --python 3.12 course-materials/exercise-data/map-qa/profile_data.py
uv run --python 3.12 --with geopandas==1.2.0 --with pyarrow==23.0.1 python -c "<odczyt obu warstw, is_valid, to_crs(2180)>"
uv run --python 3.12 course-materials/exercise-data/map-qa/download_photos.py --verify-only
uv run --python 3.12 course-materials/exercise-data/map-qa/signs/build_signs.py --verify-only
```

Dodatkowe zapytania DuckDB (schemat zagnieżdżonych kolumn Overture, rozkłady tagów OSM, crosswalk Overture→OSM) uruchomiono jednorazowym skryptem poza repozytorium; wyniki poniżej.

## Integralność plików względem `sources.json`

| Plik | Rozmiar | SHA-256 |
|---|---|---|
| `osm_roads.parquet` | zgodny | zgodny |
| `overture_segments.parquet` | zgodny | zgodny |
| `mapillary_detections.json.gz` | zgodny | zgodny |
| `photos.csv`, `photo_road_links.csv`, `reference_labels.csv`, `traffic_signs.geojson`, `osm_roads_sample.geojson` | **niezgodny** | **niezgodny** |

**Przyczyna:** `core.autocrlf=true` na VM i brak reguły w `.gitattributes` dla plików danych — Git zapisuje je w kopii roboczej z CRLF (`git ls-files --eol`: `i/lf w/crlf`). Blob w repozytorium ma poprawny hash (`git show HEAD:…/photos.csv | sha256sum` = `93157c47…` jak w `sources.json`). Bez decyzji AC-02 (przerwanie przy niezgodnym hashu) zablokuje każdy run na Windows. Patrz „Decyzje do podjęcia”.

`signs/build_signs.py --verify-only`: `checked=119 downloaded=0 missing=0` (zdjęcia i wycinki zgodne).

## Liczności, CRS, geometria

| Warstwa | Wiersze | Unikalne ID | Niepoprawne geometrie | CRS | `to_crs(2180)` |
|---|---|---|---|---|---|
| OSM roads | 99 768 | 99 768 | 0 | EPSG:4326 | OK |
| Overture segments | 85 405 | 85 405 | 0 | OGC:CRS84 | OK |
| photos.csv | 561 (Panoramax 461 / 56 sekwencji, Mapillary 100 / 52 sekwencje) | — | — | — | — |
| photo_road_links.csv | 561 | — | — | — | — |

Zgodne z PRD AC-03 i ADR-000 §5.1.

## OSM: kompletność atrybutów

| highway | drogi | maxspeed | surface | lanes | lit |
|---|---|---|---|---|---|
| service | 72 113 | 1 997 | 17 390 | 849 | 3 379 |
| residential | 11 799 | 5 467 | 9 598 | 2 334 | 5 103 |
| track | 4 296 | 2 | 1 657 | 0 | 86 |
| tertiary | 3 838 | 2 839 | 3 772 | 2 888 | 2 451 |
| secondary | 2 073 | 1 897 | 2 065 | 2 015 | 1 633 |
| living_street | 1 938 | 1 140 | 1 524 | 109 | 638 |
| primary | 1 586 | 1 539 | 1 584 | 1 562 | 1 260 |
| unclassified | 880 | 316 | 770 | 342 | 331 |
| motorway | 459 | 453 | 453 | 454 | 213 |
| pozostałe `*_link`, trunk, road, busway | 786 | 640 | 753 | 720 | 495 |

Drogi `tertiary` i wyższe z `*_link`: **8 739**; bez `maxspeed` (i bez `maxspeed:forward`) **1 210**, bez `surface` **115** — szacunek pozycji `missing` w etapie 1 (AC-13).

### `maxspeed*`
- Kolumna `maxspeed`: wyłącznie liczby całkowite (0 wartości nieliczbowych); najczęstsze 50 (5 737), 30 (4 802), 20 (2 053), 70, 40; brak w 83 478 drogach.
- Typy domniemane są w osobnym tagu `maxspeed:type`: `PL:urban` 1 603, `PL:zone30` 564, `sign` 253, `PL:zone40` 59, `PL:rural` 55, `PL:zone20` 27, `PL:living_street` 12, `PL:zone` 5.
- `maxspeed:forward` 261, `maxspeed:backward` 247; przy obu tagach wartości różne w 223 drogach, równe w 2.
- `maxspeed:conditional` 92, jedna postać: `110 @ (Mo-Fr 06:00-18:00)`.
- `maxspeed:hgv/bus/trailer` obecne (próbka GeoJSON).

### `surface`, `lit`, dostęp
- `surface`: brak 60 202; asphalt 23 313, paving_stones 7 631, gravel 1 395, concrete 1 153, ground 1 050, paved 846, unpaved 795, grass 672, dirt 581, fine_gravel 451, sett 443, compacted 437, concrete:plates 396, grass_paver 196, dalej < 100. Literówki i wartości lokalne (np. `contrete:plates`, `paving_Stones`, `ompacted`, `utwardzona`, `kostka_/_płyty_chodnikowex`, `bad`) — łącznie kilkanaście dróg.
- `lit`: brak 84 179, yes 14 534, no 1 014, 24/7 27, automatic 13, disused 1.
- `access` ∈ {private, no}: 15 000 dróg; `motor_vehicle` ∈ {private, no}: 1 096; `bridge` 781; `tunnel` 827; `boundary_crossing` 560.

## Overture: schemat i reguły

Typy kolumn (DuckDB `DESCRIBE`):
- `speed_limits`: lista `STRUCT(min_speed{value,unit}, max_speed{value INTEGER, unit}, is_max_speed_variable BOOLEAN, when{during, heading, using[], recognized[], mode[], vehicle[]{dimension, comparison, value, unit}}, between DOUBLE[])`.
- `road_surface`: lista `STRUCT(value, between DOUBLE[])`.
- `sources`: lista `STRUCT(property, dataset, license, record_id, update_time, confidence, between, provider, resource, version)`.
- `connectors`: lista `STRUCT(connector_id, at)`; także `road_flags`, `access_restrictions`, `level_rules` z `between`.

Zgodne z ADR-001 §4.2.

| Miara | Wartość |
|---|---|
| Segmenty z regułami prędkości | 12 847; z 1 regułą 11 936, z ≥ 2: 911 (do 13 reguł) |
| Reguły prędkości wg `when` / `between` | bez obu 11 841; tylko `between` 1 484; `when` + `between` 441; tylko `when` 439 |
| Jednostki | wyłącznie `km/h` |
| `when` | `mode` 427; `heading` forward 212 / backward 209 (+13 z `mode`); `during` 19 |
| `is_max_speed_variable = true` | 16 reguł |
| `road_surface` wartości | paved, paving_stones, unpaved, gravel, dirt, unknown, metal; ~5 tys. reguł z `between` |
| Klasy | service 60 968, residential 11 185, track 3 663, tertiary 3 102, living_street 2 278, secondary 1 335, primary 916, unknown 844, unclassified 816, motorway 211, trunk 87 |

### Crosswalk Overture → OSM (`sources.record_id` = `w<osm_id>@<wersja>`)
- Segmenty z referencją OSM: 84 614 z 85 405.
- Drogi OSM z pliku z co najmniej jednym segmentem: **99 416 z 99 768**.
- Segmentów na drogę: 1 → 95 667 dróg; 2 → 3 015; 3 → 661; ≥ 4 → 498 (do 12).
- 4 `record_id` z prefiksem `w` bez `@wersja` — parser musi to tolerować.
- Overture odwołuje się łącznie do 99 848 identyfikatorów dróg, więc część referencji wskazuje drogi spoza wycinka OSM (inne filtry i daty snapshotów).

## Zdjęcia i połączenia

| Miara | Wartość |
|---|---|
| Zdjęcia z kandydatem OSM / Overture | 558 / 558 z 561 |
| Dystans aparat–droga | min 0,0; mediana 2,43; p95 9,82; max 22,17 m |
| `match_method` | osm_source_reference 557, none 3, spatial_fallback 1 |
| Flagi | ambiguous_candidates 65, camera_against_way_direction 35, panorama_heading_ambiguous 31, poor_heading_alignment 27, boundary_crossing 27, missing_heading 15, service_way 14, no_osm_within_25m 3, overture_spatial_only 1 |
| Zdjęcia bez kierunku | 15 (Panoramax) |
| Pliki lokalne | `offline/` 40; `data/photos/` 0; brak 521 (wymagają `download_photos.py`) |
| `signs/` | 119 kadrów i wycinków lokalnie, hashe zgodne |

### Etykiety `certain` dostępne lokalnie (bez pobierania)
- `signs/labels.csv` (prędkość): 115 `certain` — wszystkie kadry lokalne.
- `reference_labels.csv` w `offline/` (40 zdjęć, 31 sekwencji): surface 35, junction_visible 30, street_lighting_visible 25, speed_limit_value 7.

Wystarcza na próbkę etapu 1 z ADR-002 §4.7 (13 par prędkości + 12 nawierzchni) bez pobierania zdjęć.

## Przykłady połączeń
- `panoramax_334a574d…`: droga 346304716, 0,39 m, `bearing_diff` 0,15°, `osm_source_reference`, bez flag — pewne.
- `panoramax_646ecfdd…`: droga 648167637, 5,21 m, `bearing_diff` 87,9°, flaga `poor_heading_alignment` — niepewne (próg 30°).
- `mapillary_1931009810597411` (`signs/`): droga 187014751 residential, 7,84 m, `heading_diff` 1,2°, `maxspeed` 40; Mapillary wykrył `maximum-speed-limit-20` — przykład, że wartość znaku na zdjęciu nie musi dotyczyć tej drogi ani kierunku.

## Ograniczenia
- Databricks (`workspace.map_qa`), Mapillary, Panoramax i Overture przez sieć — nieodpytane; porównanie liczności plik ↔ tabela do wykonania z tokenem od prowadzącego.
- Profil nie otwierał ręcznie zdjęć; ocena „właściwa jezdnia” dla przykładów niepewnych pozostaje do Manual QA w kroku 3.
- Liczności dotyczą snapshotu OSM 2026-11-01 i Overture 2026-10-21.0.

## Porównanie z ADR i decyzje do podjęcia
1. **Hash a końce linii (blokuje krok 1).** Do wyboru:
   - (a) reguła w `.gitattributes`: pliki danych `course-materials/exercise-data/**` bez konwersji końców linii (`-text`) i ponowny checkout tych plików — hash zgodny z `sources.json`;
   - (b) `ingest` liczy hash plików tekstowych po zamianie CRLF → LF — słabsza kontrola, bez zmiany repozytorium.
   Rekomendacja: (a), bo to błąd konfiguracji repozytorium, nie danych; wymaga zgody (zmiana wspólnego pliku i katalogu materiałów).
2. ADR-001 §4.1: wartości `PL:*` występują w `maxspeed:type`, nie w `maxspeed`; reguła „`implicit` → `not_comparable`” w praktyce nie zadziała na tych danych. Bez zmiany decyzji — `maxspeed:type` zostaje informacyjny.
3. ADR-001 §4.3: dopisać do mapowania Overture `paving_stones` → paved, `gravel`/`dirt` → unpaved, `unknown` → `not_comparable`; literówki OSM pozostają `not_comparable`.
4. ADR-001 §3.3: parser `record_id` toleruje brak `@wersja`.
5. ADR-001 §3.4 krok 7: `access` ∈ {private, no} ma 15 000 dróg (głównie `service`); dla zdjęć to 14 flag `service_way` i nieznana liczba dróg z ograniczonym dostępem — zmierzyć w kroku 3 względem wyzwalacza D-103 (> 50%).
