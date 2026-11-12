# Plan implementacji — kontrola mapy

**Data:** 2026-11-03 · **Gałąź:** `worktree-map-qa-prototype`
**Źródła:** [AGENTS.md](../AGENTS.md), [PRD](PRD.md), [ADR-000](ADR/000-main-architecture.md), [ADR-001](ADR/001-dane-normalizacja-dopasowanie.md), [ADR-002](ADR/002-odczyt-zdjec-modelami.md), [ADR-003](ADR/003-raport-i-dashboard.md)
**Stan wyjściowy:** `app/` zawiera tylko README. Kroki 0a i 0b zrobione (uv 0.13.7, Python 3.12.16; `reports/map-qa/profile.md`, commit `d617668`).

Wykonawca: Codex dla kroków bez modeli i raportu (M5, M7), Claude Code dla kroku z modelami (M6). Każdy krok to samodzielne zlecenie: agent czyta pliki z kolumny „Wejścia”, nie rusza plików spoza „Pliki”, kończy pokazaniem diffu i czeka na przegląd. Jeden agent edytuje dany plik w danej chwili.

---

## Zasady wspólne dla każdego kroku

1. **Red:** najpierw testy z kryteriów PRD/ADR wymienionych w kroku; uruchomienie i pokazanie, że padają z oczekiwanego powodu (brak funkcji, zła wartość), nie z błędu składni lub importu.
2. **Green:** minimum kodu, aż testy przejdą.
3. **Refactor:** tylko przy zielonych testach.
4. **Weryfikacja — cztery osobne kontrole w podsumowaniu:**
   - import/kompilacja: `uv run python -c "import map_qa"`;
   - testy: `uv run pytest` z liczbą zebranych, przeszłych i pominiętych (z powodami);
   - rzeczywisty CLI na plikach map-qa z kodem wyjścia;
   - ręczne sprawdzenie jednego wyniku od wejścia do raportu.
5. Wejścia w `course-materials/exercise-data/map-qa/` (poza `data/`) bez zmian w `git status`.
6. Commit po zweryfikowanym kroku: `Area: short summary`, bez push.

## Ochrona kosztu (obowiązuje cały plan)

- Domyślne limity modeli = 0; kroki 0a–5, 7–9 nie wykonują żadnego płatnego żądania.
- Płatne żądania tylko w kroku 6, po zgodzie użytkownika na konkretny manifest i przydziale budżetu przez prowadzącego.
- Limit obejmuje wszystkie próby i błędy: Luna ≤ 25, Jev ≤ 5, drugi stopień ≤ 10, `--max-cost-usd` jawnie podany.
- Zero automatycznych retry (także w SDK), timeout 40 s, pierwszy błąd wyłącza model w runie.
- Agent sprawdza tylko obecność `OPENROUTER_API_KEY`; nie czyta `.env`, nie wypisuje wartości.

---

## Etapy

| # | Krok | Wejścia | Wyjścia / pliki | Zależy od | Kryteria | Agent |
|---|---|---|---|---|---|---|
| 0a ✅ | Środowisko | AGENTS.md | `uv --version` w raporcie kroku | — | — | Użytkownik + agent |
| 0b ✅ | Profil danych | README danych, `sources.json`, `profile.sql` | `reports/map-qa/profile.md` | 0a | ADR-000 §5.1, ADR-001 §2 | Codex |
| 0c | Decyzje z profilu | `profile.md` „Porównanie z ADR”, ADR-001 | `.gitattributes`, ADR-001 §3.4, §4.1 | 0b | AC-02 na Windows, ADR-001 §3.3/§3.4/§4.3 zgodne z profilem | Claude Code |
| 1 | Szkielet i integralność | ADR-000 §3–4, §6 | `app/pyproject.toml`, `uv.lock`, `.python-version`, `src/map_qa/{config,ingest,cli}`, `tests/` | 0c | AC-01–AC-03, TAC-05 | Codex |
| 2 | Normalizacja | ADR-001 §4.1–4.3 | `src/map_qa/normalize`, `tests/unit/` | 1 | AC-12, TAC-001-01, TAC-001-04 | Codex |
| 3 | CRS i ocena połączeń | ADR-001 §3.2–3.4 | `src/map_qa/matching`, `tests/` | 1 | AC-04, AC-06–AC-09, TAC-001-02/03 | Codex |
| 4 | Kategorie i raport bez modelu | ADR-001 §3.5, ADR-003 §3.1 | `src/map_qa/{compare,report,templates}` | 2, 3 | AC-05, AC-10–AC-16, AC-21, AC-24–AC-26 | Codex (M5 + M7) |
| 5 | Vision bez płatnych wywołań | ADR-002 §3–4 | `src/map_qa/{vision,store,evaluation}`, `config/thresholds.toml` | 4 | AC-17–AC-20f, AC-22, AC-23 (na transporcie testowym) | Claude Code (M6) |
| 6 | Próba z przydziałem | ADR-002 §4.5, §4.7 | capture w `tests/fixtures/captures/`, run w `reports/map-qa/runs/` | 5 + zgoda + budżet | AC-19–AC-23 na rzeczywistym API | Claude Code (M6) |
| 7 | Etap 2 PRD: oświetlenie i skrzyżowanie | ADR-001 §4.4 | rozszerzenie `normalize`, `compare`, pytania v2 | 4 (6 opcjonalnie) | AC-32 | Codex |
| 8 | Dashboard | ADR-003 §3.2–3.3 | `app/dashboard/app.py`, `.streamlit/config.toml`, `store` | 4 | AC-27–AC-30, TAC-003-* | Codex |
| 9 | Przegląd końcowy | wszystko | uwagi w PR / issue | 1–8 | AC-31–AC-33 | Claude Code (review) |

Kroki 2 i 3 są niezależne (różne pliki) i mogą iść równolegle w osobnych worktree. Krok 8 może startować po kroku 4, równolegle z 5–7.

---

## Szczegóły kroków

### 0a. Środowisko — ✅ zrobione 2026-11-03 (uv 0.13.7 przez winget, Python 3.12.16)
- Instalacja uv przez menedżer pakietów (preferowane): `winget install --id=astral-sh.uv -e`, alternatywnie oficjalny instalator z https://docs.astral.sh/uv/getting-started/installation/. Wymaga zgody użytkownika przy uruchomieniu.
- Nowe okno terminala, potem `uv --version` i `uv python install 3.12`.
- **Koniec:** `uv --version` działa w powłoce agenta.

### 0b. Profil danych (bez kodu aplikacji) — ✅ zrobione 2026-11-03, commit `d617668`
- `uv run --python 3.12 course-materials/exercise-data/map-qa/profile_data.py`; kontrola GeoPandas i EPSG:2180 z README danych.
- Wypisanie typów kolumn `speed_limits`, `road_surface`, `sources` z `overture_segments.parquet`.
- Rozkład wartości `maxspeed*` i `surface` w OSM; liczności flag w `photo_road_links.csv`; dostępność zdjęć lokalnych (`download_photos.py --verify-only`).
- Databricks `compare-counts` ręcznie z DATABRICKS.md, jeśli token jest dostępny; inaczej zapis ograniczenia.
- **Koniec:** `profile.md` z poleceniami, wersjami, hashami, licznościami; porównanie z ADR-000 §5.1. Rozbieżność → aktualizacja ADR przed krokiem 1.
- **Commit:** `Docs: map QA data profile`.

### 0c. Decyzje z profilu (blokuje krok 1)
- **Hash a CRLF** (`profile.md` decyzja 1): 5 plików tekstowych ma niezgodny SHA-256 przez `core.autocrlf=true`. **Wybrany wariant (a)** (2026-11-12): reguła `course-materials/exercise-data/** -text` w `.gitattributes` i ponowny checkout tych plików; ADR-001 §3.1 bez zmian. Odrzucony (b): hash po zamianie CRLF → LF w `ingest` — słabsza kontrola.
- **ADR-001 §3.3** (`@wersja` opcjonalna) i **§4.3** (wartości Overture): wprowadzone w `d617668`; tu tylko kontrola zgodności z profilem.
- **ADR-001 §3.4 krok 7:** dopisany pomiar udziału zdjęć z `ambiguous_link` przez ograniczony dostęp w kroku 3 względem D-103 (> 50%).
- **ADR-001 §4.1:** bez zmiany decyzji; nota, że `PL:*` występuje w `maxspeed:type`, nie w `maxspeed`.
- **Koniec:** `sha256sum` 5 plików tekstowych zgodny z `sources.json`; `git status` czysty w `course-materials/exercise-data/`; `git diff` ADR przejrzany.
- **Commit:** `Docs: profile decisions in plan and ADR-001`; osobno `Repo: keep LF in exercise data`.

### 1. Szkielet i integralność
- Testy: zgodne hashe → OK; kopia z 1 zmienionym bajtem → `InputIntegrityError` z nazwą pliku; CLI kod 1 bez raportu; liczności 99 768 / 85 405 / 561; złe argumenty → kod 2.
- **Koniec:** `uv run map-qa check --stage 1` kończy się kodem 0 i wypisuje liczności (bez kandydatów); ręczna weryfikacja hasha jednego pliku.
- **Commit:** `App: uv scaffold, input integrity and counts`.

### 2. Normalizacja
- Testy z tabel ADR-001 §4.1–4.3 na prawdziwych wierszach (`osm_roads_sample.geojson`, wiersze Overture z ≥ 2 regułami i z `when`).
- **Koniec:** test pokazuje zachowanie surowych `maxspeed_raw` i `speed_limits_raw` bajt w bajt; CLI bez zmian zachowania.
- **Commit:** `App: normalize maxspeed, speed_limits and surface`.

### 3. CRS i ocena połączeń
- Najwyżej 6 przypadków w pierwszym podejściu: znany dystans 10 m; heading 359/1; odwrócona geometria i `oneway=-1`; brak kierunku; dwa bliskie odcinki / remis; `service_way` z `access=private`. Wiersze z `signs/signs.csv` + `signs/nearest_osm.csv` po `photo_id`.
- **Koniec:** CLI raportuje 3 zdjęcia bez kandydata i liczbę `ambiguous_link`; ręcznie otwarte jedno zdjęcie z niepewnym połączeniem i sprawdzona jezdnia.
- **Commit:** `App: CRS 2180 and photo-road link assessment`.

### 4. Kategorie i raport bez modelu
- Testy kategorii (ADR-001 §8), spójności MD/HTML/CSV, escapowania HTML, atrybucji, braku częściowego raportu, sekcji „Ograniczenia” przy niedostępnym Databricks (`compare-counts` bez zmiennych → kod 0 i wpis).
- **Koniec:** `uv run map-qa check --stage 1` tworzy raport; wszystkie odczyty `model_unavailable`; 0 żądań sieciowych; jeden kandydat `rozbieżne` odtworzony ręcznie z wejść.
- **Commit:** `App: candidate categories and Markdown/HTML/CSV report`.

### 5. Vision bez płatnych wywołań
- Testy z ADR-002 §8 na transporcie testowym; mocki API dopiero po capture (krok 6) — do tego czasu testy oparte na odpowiedzi API są pominięte z powodem „brak capture”.
- Weryfikacja w SDK 1.3.107: retry `none`, timeout dla `decisions.create`, argumenty klienta; wynik zapisany w ADR-002 §2.
- `thresholds.toml` z progiem 0,7, rezerwą kosztu, wersją pytań — zatwierdzony commitem przed krokiem 6.
- **Koniec:** run z domyślnymi limitami: 0 żądań, manifest próbki nie powstaje; run z `--decision-limit 2 --max-cost-usd 0` → kod 2.
- **Commit:** `App: vision cascade, budget and cache (no paid calls)`.

### 6. Próba z przydziałem
- Pokazanie manifestu próbki i limitów; **czekanie na zgodę użytkownika i budżet**.
- Pierwsze żądanie (`--decision-limit 1`) → capture bez sekretów → mocki z capture → odblokowanie pominiętych testów.
- Mała próba w granicach przydziału; Jev na pierwszych parach; drugi stopień tylko dla niepewnych.
- **Koniec:** raport z kosztem, liczbą żądań na model, odczytami na stopień, trafnością i pokryciem; ręcznie obejrzane wszystkie niezgodności z etykietami.
- **Commit:** `App: first paid decision trial with safe captures`.

### 7. Etap 2 PRD
- Pytania `street_lighting_visible`, `junction_visible` (`questions_version` 2); topologia przez `node_ids`; most/tunel/granica wycinka → `not_comparable`.
- **Koniec:** `uv run map-qa check --stage 2` z kodem 0; ręcznie sprawdzony jeden węzeł skrzyżowania.
- **Commit:** `App: lighting and junction checks`.

### 8. Dashboard
- Testy `store` (trwałość, historia, walidacja); E2E Playwright CLI: filtr, zapis decyzji, przeładowanie, zakładka „Do poprawy”, brak żądań poza localhost.
- **Koniec:** Manual QA ze zrzutami obu zakładek, polskie teksty, brak błędów konsoli.
- **Commit:** `App: Streamlit review dashboard`.

### 9. Przegląd końcowy
- Review diffu od commitu bazowego (hash zapisany przed krokiem 1) świeżą sesją bez kontekstu implementacji; lista niespełnionych AC.

---

## Poza zakresem planu
Wszystko z PRD §7, w tym edycja OSM, praca wielu użytkowników, trening modeli, odświeżanie snapshotu, klasa drogi/pasy/chodniki. Databricks w pipeline (tylko ręczne porównanie liczności w 0b).

## Ryzyka
| Ryzyko | Skutek | Ograniczenie |
|---|---|---|
| Schemat Overture inny niż w ADR-001 §4.2 | Błędne `not_comparable` | Krok 0b przed kodem — sprawdzone, zgodny |
| CRLF zmienia hash plików danych na Windows | AC-02 blokuje każdy run | Krok 0c, wariant (a) |
| SDK nie wspiera timeoutu w `decisions.create` | Brak limitu czasu | Weryfikacja w kroku 5; plan B: surowy POST (ADR-000 D-03) |
| Większość zdjęć Panoramax tylko online | Mała próbka nawierzchni | `download_photos.py` w 0b; próbka z plików lokalnych |
| Dużo `not_comparable` | Długa kolejka ręczna | Wyzwalacz D-102 (> 40%) |
| Próbka 25 par | Brak wniosków o modelach | Raport podaje liczności; bez porównań statystycznych |
| Dwa agenty w jednym pliku | Konflikty | Kroki 2/3 i 8 tylko w osobnych worktree |

## Pierwsza czynność
Krok 0c: reguła `-text` w `.gitattributes` dla `course-materials/exercise-data/**`, ponowny checkout plików danych i kontrola hashy z `sources.json`.

## Commit dokumentacji przed krokiem 1
Po akceptacji planu: `git add docs`, commit `Docs: PRD, ADR, plan`, zapis hasha (`git rev-parse HEAD`) jako bazy do przeglądu w kroku 9.
