# Plan implementacji — kontrola mapy

**Data:** 2026-11-03, aktualizacja 2026-11-12 · **Gałąź:** `worktree-map-qa-prototype` (kroki 0a–0b), od 2026-11-12 `map-app-implementation`
**Źródła:** [AGENTS.md](../AGENTS.md), [PRD](PRD.md), [ADR-000](ADR/000-main-architecture.md), [ADR-001](ADR/001-dane-normalizacja-dopasowanie.md), [ADR-002](ADR/002-odczyt-zdjec-modelami.md), [ADR-003](ADR/003-raport-i-dashboard.md)
**Stan wyjściowy:** `app/` zawiera tylko README. Kroki 0a, 0b i 0c zrobione (uv 0.13.7, Python 3.12.16; `reports/map-qa/profile.md`, commit `d617668`; 0c: `a275ecb`).

Wykonawcy, zależności i równoległość kroków 1–9 określa wyłącznie macierz w [planie orkiestracji](plans/map-qa-full-app-implementation-plan.md) §5–§7 (aktualizacja 2026-11-12); kolumna „Agent” poniżej jest historyczna. Każdy krok to samodzielne zlecenie: agent czyta pliki z kolumny „Wejścia”, nie rusza plików spoza „Pliki”, kończy pokazaniem diffu. Jeden agent edytuje dany plik w danej chwili.

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

- Domyślne limity modeli w aplikacji = 0 (zachowanie produktu, AC-19b). **Przydział prowadzącego 2026-11-12:** wywołania Luna Decisions, Jev i Luna LLM w testach bez limitu liczby, łącznie ≤ 1 USD na cały plan (stop przy 0,80 USD); szczegóły w [planie orkiestracji §2](plans/map-qa-full-app-implementation-plan.md).
- Testy manualne i E2E używają prawdziwych endpointów bez mocków; mocki tylko w unit/integration i wyłącznie z capture prawdziwej odpowiedzi (capture przed pierwszym mockiem, zadanie T5.2b).
- Limit obejmuje wszystkie próby i błędy: model główny Jev ≤ 25, porównawczy Luna Decisions ≤ 5, drugi stopień Luna LLM ≤ 10 (ADR-000 D-04, zmiana 2026-11-12), `--max-cost-usd` jawnie podany.
- Zero automatycznych retry (także w SDK), timeout 40 s, pierwszy błąd wyłącza model w runie.
- Agent sprawdza tylko obecność `OPENROUTER_API_KEY`; nie czyta `.env`, nie wypisuje wartości.

---

## Etapy

| # | Krok | Wejścia | Wyjścia / pliki | Zależy od | Kryteria | Agent |
|---|---|---|---|---|---|---|
| 0a ✅ | Środowisko | AGENTS.md | `uv --version` w raporcie kroku | — | — | Użytkownik + agent |
| 0b ✅ | Profil danych | README danych, `sources.json`, `profile.sql` | `reports/map-qa/profile.md` | 0a | ADR-000 §5.1, ADR-001 §2 | Codex |
| 0c ✅ | Decyzje z profilu | `profile.md` „Porównanie z ADR”, ADR-001 | `.gitattributes`, ADR-001 §3.4, §4.1 | 0b | AC-02 na Windows, ADR-001 §3.3/§3.4/§4.3 zgodne z profilem | Claude Code |
| 1 | Szkielet i integralność | ADR-000 §3–4, §6 | `app/pyproject.toml`, `uv.lock`, `.python-version`, `src/map_qa/{config,ingest,cli}`, `tests/` | 0c | AC-01–AC-03, TAC-05 | Codex |
| 2 | Normalizacja | ADR-001 §4.1–4.3 | `src/map_qa/normalize`, `tests/unit/` | 1 | AC-12, TAC-001-01, TAC-001-04 | Codex |
| 3 | CRS i ocena połączeń | ADR-001 §3.2–3.4 | `src/map_qa/matching`, `tests/` | 1 | AC-04, AC-06–AC-09, TAC-001-02/03 | Codex |
| 4 | Kategorie i raport bez modelu | ADR-001 §3.5, ADR-003 §3.1 | `src/map_qa/{compare,report,templates}` | 2, 3 | AC-05, AC-10–AC-16, AC-21, AC-24–AC-26 | Codex (M5 + M7) |
| 5 | Vision bez płatnych wywołań | ADR-002 §3–4 | `src/map_qa/{vision,store,evaluation}`, `config/thresholds.toml` | 4 | AC-17–AC-20f, AC-22, AC-23 (na transporcie testowym) | Claude Code (M6) |
| 6 | Próba z przydziałem | ADR-002 §4.5, §4.7 | capture w `tests/fixtures/captures/`, run w `reports/map-qa/runs/` | 5 + zgoda + budżet | AC-19–AC-23 na rzeczywistym API | Claude Code (M6) |
| 7 | Etap 2 PRD: oświetlenie i skrzyżowanie | ADR-001 §4.4 | rozszerzenie `normalize`, `compare`; pytania etapu 2 w `questions_version` 1 (ADR-002 §4.1) | 4 (6 opcjonalnie) | AC-32 | Codex |
| 8 | Dashboard | ADR-003 §3.2–3.3 | `app/dashboard/app.py`, `.streamlit/config.toml` (używa `store` z kroku 5) | 4, 5 (`store`, T5.1) | AC-27–AC-30, TAC-003-* | Codex |
| 9 | Przegląd końcowy | wszystko | uwagi w PR / issue | 1–8 | AC-31–AC-33 | Claude Code (review) |

Kroki 2 i 3 są niezależne (różne pliki) i mogą iść równolegle w jednym checkoucie, bez worktree (rozłączne pliki, plan orkiestracji §6). Krok 8 może startować po utworzeniu `store` (T5.1), równolegle z resztą kroku 5 i krokiem 7 (krok 6 tylko po zgodzie).

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
- Databricks `compare-counts` ręcznie z DATABRICKS.md, jeśli token jest dostępny; inaczej zapis ograniczenia. ✅ Uzupełnione 2026-11-12, commit `2de4521`: pięć tabel zgodnych z plikami.
- **Koniec:** `profile.md` z poleceniami, wersjami, hashami, licznościami; porównanie z ADR-000 §5.1. Rozbieżność → aktualizacja ADR przed krokiem 1.
- **Commit:** `Docs: map QA data profile`.

### 0c. Decyzje z profilu (blokuje krok 1) — ✅ `.gitattributes` wykonane 2026-11-12: 8/8 plików z `sources.json` zgodnych (rozmiar i SHA-256), `signs` 119/119, liczności bez zmian
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
- **Koniec:** `uv run map-qa check --stage 1` tworzy raport; brak manifestu i odczytów, pary ze zdjęciem jako jedynym dowodem mają `model_unavailable` (ADR-001 §3.5); 0 żądań sieciowych; jeden kandydat `rozbieżne` odtworzony ręcznie z wejść.
- **Commit:** `App: candidate categories and Markdown/HTML/CSV report`.

### 5. Vision bez płatnych wywołań
- Testy z ADR-002 §8 na transporcie testowym; mocki API dopiero po capture (krok 6) — do tego czasu testy oparte na odpowiedzi API są pominięte z powodem „brak capture”.
- Weryfikacja w SDK 1.3.107: retry `none`, timeout dla `decisions.create`, argumenty klienta; wynik zapisany w ADR-002 §2.
- `thresholds.toml` z progiem 0,7, rezerwą kosztu, wersją pytań — zatwierdzony commitem przed krokiem 6.
- **Koniec:** run z domyślnymi limitami: 0 żądań, manifest próbki nie powstaje; run z `--decision-limit 2 --max-cost-usd 0` → kod 2.
- **Commit:** `App: vision cascade, budget and cache (no paid calls)`.

### 6. Próba z przydziałem
- Pokazanie manifestu próbki i limitów (przydział prowadzącego 2026-11-12, łącznie ≤ 1 USD — bez czekania na osobną zgodę).
- Capture prawdziwych odpowiedzi powstaje wcześniej (T5.2b), zanim powstanie pierwszy mock; tu E2E `live` bez mocków i pełny run z limitami.
- Mała próba w granicach przydziału; model porównawczy (Luna Decisions) na pierwszych parach wysłanych do Jev; drugi stopień tylko dla niepewnych.
- **Koniec:** raport z kosztem, liczbą żądań na model, odczytami na stopień, trafnością i pokryciem; ręcznie obejrzane wszystkie niezgodności z etykietami.
- **Commit:** `App: first paid decision trial with safe captures`.

### 7. Etap 2 PRD
- Pytania `street_lighting_visible`, `junction_visible` (`questions_version` 1 — ADR-002 §4.1, decyzja 2026-11-12); run `--stage 2` jest nadzbiorem etapu 1; topologia przez `node_ids`; most/tunel/granica wycinka → `not_comparable`.
- **Koniec:** `uv run map-qa check --stage 2` z kodem 0; ręcznie sprawdzony jeden węzeł skrzyżowania.
- **Commit:** `App: lighting and junction checks`.

### 8. Dashboard
- Testy logiki dashboardu i zapisu decyzji przez `store` z kroku 5 (trwałość, historia, walidacja); E2E Playwright CLI: filtr, zapis decyzji, przeładowanie, zakładka „Do poprawy”, brak żądań poza localhost.
- **Koniec:** Manual QA ze zrzutami obu zakładek, polskie teksty, brak błędów konsoli.
- **Commit:** `App: Streamlit review dashboard`.

### 9. Przegląd końcowy
- Review diffu od commitu bazowego `63974fe` (plan orkiestracji; zastępuje hash zapisywany przed krokiem 1) świeżą sesją bez kontekstu implementacji; lista niespełnionych AC.

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
| Dwa agenty w jednym pliku | Konflikty | Rozłączne „Editable files” i hotspoty z jednym właścicielem (plan orkiestracji §5–§7), jeden checkout |

## Status wykonania (2026-11-12, plan orkiestracji)

| Krok | Status | Wykonawca (faktyczny) | Dowód |
|---|---|---|---|
| T0.1–T0.2 | ✅ | O; smoke CL/CS/OC/H | `8e6a1b7`; Codex sandbox blokuje `.git/`; OC brak wyjścia headless → zadania OC do CL; H próbował `git commit` mimo zakazu (zablokował klasyfikator) |
| 1 (T1.1–T1.4) | ✅ | O (testy, fixtures), CL (Green) | `91e4702`, `3f7914d`, `3503251` |
| 2 (T2.1–T2.2) | ✅ | O (testy), CL | `00d79e3`; O dodał obsługę numpy z Parquet |
| 3 (T3.1–T3.2) | ✅ | O (testy), CS | `8190121`; 434/124/3, mismatch 0% |
| 4 (T4.1–T4.5) | ✅ | O (`compare`, `cli`), CL (`report`, `sources_remote`) | `e130c85`, `fab3dd8`, `8050638`, `985ba4f`; capture Databricks |
| R-A | ✅ | CS review + O | 3 uwagi P2 naprawione w `0bce4ac` |
| 5 (T5.1–T5.6) | ✅ | O (`store`, testy vision, capture, integracja), CL (research SDK, `evaluation`), CS (`vision`) | `3fda90a`, `bfec839`, `353c042`, `a13e58e`, `f67a99c`, `7ef7693` |
| 6 (T6) | ✅ | O | `70bcff2`; E2E `live` 4/4; próba 40 żądań, 0,006367 USD; drugi run 0 żądań |
| 7 (T7.1–T7.3) | ✅ | O | `c26e6db`, `0cd26da`; logika etapu 2 powstała w T4.2 (testy T7 bez fazy Red) |
| 8 (T8.1–T8.3) | ✅ kod, Manual QA w toku | O (testy, decyzja wizualna), CL (dashboard) | `52902d4`, `b73d1c8` |
| 9 (R-F, T9) | w toku | — | — |

**Koszt płatnych wywołań (przydział ≤ 1 USD):** capture T5.2b 0,00034 USD; E2E `live` ≈ 0,0005 USD; próba T6 0,006367 USD; łącznie ≈ **0,0072 USD**.

**Eskalacje i odstępstwa:** `compare` i testy T1.2/T2.1/T3.1/T4.1/T5.3/T7.1/T8.2 napisał O zamiast H (kontrakty współdzielone; H nie respektował zakazu Git w smoke teście). Zadania OC (T4.3, T8.3) wykonał CL. Worker T5.4 (CS) wykrył 2 błędne oczekiwania w testach O (koszt BYOK, rezerwa) — poprawione testy, nie logika. Push na `origin` po milestone zablokowany przez klasyfikator uprawnień — wymaga decyzji człowieka.

## Pierwsza czynność
~~Krok 0c~~ — wykonany 2026-11-12. Następna czynność: T0.1 z planu orkiestracji.

## Commit dokumentacji przed krokiem 1
Po akceptacji planu: `git add docs`, commit `Docs: PRD, ADR, plan`, zapis hasha (`git rev-parse HEAD`) jako bazy do przeglądu w kroku 9. Aktualizacja 2026-11-12: bazą przeglądu jest `63974fe`.
