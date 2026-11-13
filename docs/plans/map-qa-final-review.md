# Review końcowy R-F: zgodność z PRD i ADR

**Data:** 2026-11-13 · **Gałąź:** `map-app-implementation` · **Baza review:** `63974fe` · **Plan:** [map-qa-full-app-implementation-plan.md](map-qa-full-app-implementation-plan.md) §9.6

Źródła oceny: review Codex `gpt-6.1-sol` (`codex exec review`), niezależna świeża sesja Claude bez kontekstu implementacji, Manual QA orkiestratora (CLI na pełnych danych, Playwright CLI dla dashboardu). Wszystkie uwagi blokujące i istotne z obu review zostały naprawione (`dc0cd13`, `c74c272`).

## Działanie aplikacji (osobno od testów)

| Kontrola | Wynik |
|---|---|
| `uv run map-qa check --stage 1` | kod 0, 58–83 s, 0 połączeń sieciowych; 99 768 / 85 405 / 561 / 1 730; połączenia 434 / 124 / 3 |
| `uv run map-qa check --stage 1 --decision-limit 25 --comparison-limit 5 --fallback-limit 10 --max-cost-usd 1` | 40 żądań (25/5/10), 0 błędów, 0,006367 USD; ponownie na finalnym kodzie: 0 żądań (cache) |
| `uv run map-qa check --stage 2` (bez i z limitami) | kod 0; z limitami 25 nowych żądań, 0,0032 USD; pary etapu 1 zawarte (P4) |
| `uv run map-qa compare-counts` | 5/5 tabel zgodnych z Databricks; bez zmiennej → wpis „Ograniczenia”, kod 0 |
| Dashboard (Playwright CLI) | zrzuty „Przegląd” i „Do poprawy”; filtr „rozbieżne” = 27 jak w raporcie; zapis decyzji; restart serwera — decyzja widoczna w obu zakładkach; konsola 0 błędów/ostrzeżeń; żądania tylko `http://localhost:8501` |
| Wejścia | `git status course-materials` czysty po testach i runach (AC-01, TAC-03) |

## Kryteria akceptacji PRD

| AC | Status | Dowód |
|---|---|---|
| AC-01 | spełnione | `ingest.verify_inputs` przed i po runie (`cli.check`); `tests/e2e/test_stage1_cli.py::test_inputs_unchanged`, `tests/integration/test_cli_exit_codes.py::test_post_run_hash_check_exit_1_no_report` |
| AC-02 | spełnione | `test_changed_byte_exit_1_no_report` (kod 1, nazwa pliku, brak raportu) |
| AC-03 | spełnione | `run.json.input_counts`; raport „Liczności wejść” |
| AC-04 | spełnione | `matching.require_metric`, `to_crs(2180)`; raport „CRS: EPSG:2180” |
| AC-05 | spełnione | „Ograniczenia”: Databricks (D-02) + stan OpenRouter w każdym runie |
| AC-06 | spełnione | `matching.assess_links`; `tests/unit/test_matching.py` |
| AC-07 | spełnione | `compare.categorize`; `test_compare.py` (niepewne zdjęcie nigdy nie daje `rozbieżne`) |
| AC-08 | spełnione | `heading` NaN vs 0; raport „zdjęcia bez kierunku: 15” |
| AC-09 | spełnione | 434 + 124 + 3 = 561; `test_matching_data.py` |
| AC-10, AC-10a | spełnione | `test_compare_data.py`, `test_stage2_data.py`; zamknięta lista przyczyn w kolejności kanonicznej |
| AC-11 | spełnione | `rozbieżne` tylko przy porównywalnych wartościach; ręczne odtworzenie drogi 19803664 z wejść |
| AC-12 | spełnione | `normalize` (warunkowe, kierunkowe, wielokrotne, jednostki, `between`); most/tunel dla skrzyżowania |
| AC-13 | spełnione | `missing` tylko `tertiary`+ z adnotacją „brak atrybutu” |
| AC-14 | spełnione | brak „błąd mapy” w raportach i tabelach bez decyzji (`test_report.py`, `test_dashboard_logic.py`) |
| AC-15 | spełnione | kolumny kandydata w MD/HTML/CSV (+ `link_details`) |
| AC-16 | spełnione | bilans kandydaci + wykluczenia = pary; wykluczenia próbki modelu w raporcie |
| AC-17 | spełnione | `vision.build_*_request` (tekst + obraz); `test_vision_request.py` |
| AC-18 | spełnione | `interpret_decision` / `interpret_chat` (zamknięta lista) |
| AC-19, AC-19a–c | spełnione | `store.budget_reserve`, retry `none` (`test_vision_transport.py`: 1 żądanie przy 503); manifest 13 + 12 par, podział po `sequence`, `fsync` przed żądaniem |
| AC-20, AC-20a–f | spełnione | `test_vision_cascade.py`; `vision_summary` sumuje się do liczby odczytów; stopień w raporcie i dashboardzie |
| AC-21 | spełnione | run bez limitów: 0 żądań (zablokowany socket w E2E) |
| AC-22 | spełnione | ponowny run 0 żądań; `test_vision_live.py::test_rerun_uses_cache_no_new_requests` |
| AC-23 | spełnione (wg brzmienia: raport podaje trafność i pokrycie per pytanie na etykietach `certain` z licznikiem `uncertain`; progi zapisane w `thresholds.toml` commitem `c13d848` przed próbą) | `evaluation.evaluate`; `run.json.evaluation`; sekcja „Ewaluacja” raportu. **Wynik względem progów — patrz wiersz niżej** |
| Progi akceptacji odczytu (AC-23, ADR-002 §4.10; `min_coverage` 0,3, `min_accuracy` 0,8) — **próba końcowa v2 na podziale `test`** (zasady zapisane przed próbą, `8e74b68`) | prędkość 0,833 — **spełnione**; nawierzchnia 1,0 — **spełnione**; oświetlenie 1,0 — **spełnione**; skrzyżowanie 0,0 (3 pary) — **niespełnione** (rozjazd definicji pytania i etykiet referencyjnych, ADR-002 §4.1) | prędkość: pokrycie 1,0, trafność **0,769 — niespełnione**; skrzyżowanie: pokrycie 1,0, trafność **0,333 — niespełnione**; nawierzchnia 1,0 / 1,0 — spełnione; oświetlenie 1,0 / 0,833 — spełnione (`run.json.evaluation_thresholds.met`, runy `20261113T083911Z-bf8259`, `20261113T081129Z-1bb5d9`). Progów ani pytań nie zmieniano po próbie |
| AC-24 | spełnione | ta sama liczba pozycji w MD/HTML/CSV (`test_stage1_cli.py`) |
| AC-25 | spełnione (po poprawce R-F `dc0cd13`) | wcześniej dashboard nie miał atrybucji zdjęć par `zgodne` (uwaga audytu P1); teraz `cli.check` zapisuje atrybucję każdego zdjęcia kandydata, także `zgodne` i `signs/`; test `tests/e2e/test_stage1_cli.py::test_every_candidate_photo_has_attribution`; Manual QA: podpis „autor · licencja · źródło” pod zdjęciem (zrzut `qa-04`) |
| AC-26 | spełnione | sekcja „Źródła”, wersja pytań, hash commitu progów |
| AC-27 | spełnione | filtry atrybut/kategoria/etap/przyczyna z licznikiem (AppTest + Playwright: 27) |
| AC-28 | spełnione | SQLite WAL; trwałość po restarcie serwera (Playwright) |
| AC-29 | spełnione | „Do poprawy”: tylko `confirmed_error`, odnośnik OSM, wartość proponowana, zdjęcie |
| AC-30 | spełnione | zdjęcia tylko z plików lokalnych; telemetria wyłączona; brak „Deploy”; żądania tylko `localhost` |
| AC-31 | spełnione | AC-01–AC-26 dla prędkości i nawierzchni |
| AC-32 | **niespełnione w części skrzyżowania** (AC-10–AC-16 spełnione dla oświetlenia i skrzyżowania; pomiar AC-23 wykonany; próg trafności skrzyżowania niespełniony) | `tests/integration/test_stage2_data.py`, `tests/e2e/test_stage2_cli.py`; run etapu 2 z modelem `20261113T081129Z-1bb5d9`; trafność skrzyżowania 0,333 < 0,8 (wiersz „Progi akceptacji odczytu”) |
| AC-33 | spełnione | AC-27–AC-30 na runie etapu 2 (zawiera etap 1) |

## Uwagi z review i ich status

| Źródło | Uwaga | Status |
|---|---|---|
| Codex R-A | publikacja raportu przed zapisem runu; brak `LinkAssessment`; `|` w tabelach MD | naprawione `0bce4ac` |
| Codex R-F P1 | zdjęcia `signs/` nie były dowodem prędkości | naprawione `dc0cd13` |
| Codex R-F P1 / audyt P5 | formularz decyzji przenosił wartości na innego kandydata | naprawione `dc0cd13` (+ testy AppTest) |
| Codex R-F P2 | brak kontroli hasha zdjęcia próbki; brak liczników wykluczeń próbki; brak zdjęcia w „Do poprawy” | naprawione `dc0cd13` |
| Audyt P1 (AC-25) | atrybucja zdjęć par `zgodne` w dashboardzie | naprawione `dc0cd13` |
| Audyt P2 | tabela kandydatów MD nie renderowała się (13 vs 14 kolumn) | naprawione `dc0cd13` |
| Audyt P3 (AC-32) | brak pomiaru etapu 2 z modelem | wykonane: run `20261113T081129Z-1bb5d9`; wynik progów w tabeli AC |
| Audyt P4 (TAC-003-02) | brak QA przeglądarkowego | wykonane: Playwright CLI (zrzuty, konsola, sieć, restart) |
| Audyt P6–P10, P13 | stare runy, węzeł stopnia 2, `compare-counts`, połączenie SQLite, kolejność przyczyn, `.gitignore` | naprawione `dc0cd13`; runy powtórzone na finalnym kodzie |
| Audyt P11 | odpowiedzi spoza listy nie są cache'owane | bez zmiany: odpowiedź Decisions z `choice` spoza listy jest cache'owana (`answer` ≠ None); błędy HTTP celowo nie (ADR-002 §4.9) |
| Audyt P12 / Manual QA (D-302) | 51 tys. wierszy w dashboardzie ~27 s | naprawione `c74c272` |

Uwag blokujących otwartych: **brak**. **Niespełnione:** próg trafności odczytu skrzyżowania (próba v2, podział `test`). Zadziałał wyzwalacz przeglądu ADR-002 D-201 (pokrycie 1,0 > 95%).

## Techniczne kryteria akceptacji

| TAC | Status | Dowód |
|---|---|---|
| TAC-01 | spełnione | pełny `uv run pytest`: 322 passed, 4 deselected (`live`), 0 skipped (13 min); ≥ 1 test na moduł; `pytest -m live`: 4 passed |
| TAC-02 | spełnione | etap 1: kod 0, < 5 min, bez sieci |
| TAC-03 | spełnione | `course-materials` czyste |
| TAC-04 | spełnione | `test_stage1_cli.py::test_no_secrets_and_no_base64_in_run_dir`; skan capture |
| TAC-05 | spełnione | `pyproject.toml` — wszystkie zależności `==` |
| TAC-001-01 | spełnione (semantycznie) | `test_compare_data.py::test_raw_values_identical_to_input` (porównanie JSON) |
| TAC-001-02 | spełnione | `matching.CRSError` |
| TAC-001-03 | spełnione | 3 bez kandydata, 124 niepewne |
| TAC-001-04 | spełnione | `test_multi_rule_overture_never_decides_without_model` |
| TAC-002-01 | spełnione | ledger = wywołania transportu (`test_vision_cascade.py`, `test_vision_live.py`) |
| TAC-002-02 | spełnione | brak `base64,` w runach i capture |
| TAC-002-03 | spełnione | sekcja „Modele” (koszt BYOK z `upstream_inference_cost`) |
| TAC-002-04 | spełnione | `tests/unit/vision_support.py` — mocki wyłącznie z plików capture |
| TAC-003-01 | spełnione | liczba wierszy równa w 3 formatach |
| TAC-003-02 | spełnione (Manual QA) | zrzuty obu zakładek przez Playwright CLI, konsola bez błędów, polskie teksty (wyjątek: wbudowane „Select all” Streamlit) |
| TAC-003-03 | spełnione | restart serwera Streamlit — decyzja widoczna w obu zakładkach |

## Ograniczenia, niespełnione i niezweryfikowane

- **Niespełnione:** próg trafności odczytu skrzyżowania. Próba v1 (oba podziały): prędkość 0,769, skrzyżowanie 0,333; próba końcowa v2 (podział `test`, za zgodą użytkownika): prędkość 0,833, nawierzchnia 1,0, oświetlenie 1,0, skrzyżowanie 0,0. Domknięcie wymaga nowych etykiet skrzyżowania zgodnych z promieniem 25 m. Zadziałał wyzwalacz przeglądu D-201 (pokrycie > 95%). Nie zmieniano progów ani pytań po próbie (AC-23 zabrania korekty po wyniku). Próby są małe (13 i 6 par); 2 z 3 niezgodności prędkości to etykiety przygotowane dla wycinka innego znaku niż widoczny B-33 (PRD §8, §12); dla skrzyżowania pytanie nie ogranicza odległości (ADR-002). Dalszy krok wymaga decyzji człowieka: nowa wersja pytań (`questions_version = 2`) i próba na podziale `test` albo korekta etykiet.
- E2E dashboardu w przeglądarce wykonano jako Manual QA przez Playwright CLI, bez automatycznego testu przeglądarkowego w `pytest`.
- Raporty MD/HTML dla etapu 2 mają po kilka MB (≈ 4 tys. pozycji listy).
- Push i PR — za zgodą użytkownika 2026-11-13; merge pozostaje decyzją człowieka.
