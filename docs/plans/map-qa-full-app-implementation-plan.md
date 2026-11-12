# Plan implementacji całej aplikacji map-qa (orkiestracja agentów)

> **Status: ZAAKCEPTOWANY 2026-11-12** — wykonanie autoryzowane przez użytkownika jako cel „zaimplementuj cały plan”. Decyzje: G-DESIGN → domyślny motyw Streamlit; G-PUB → push na `origin` po każdym milestone; PR na każdy milestone (A–D). G-PAID bez zmian (T6 tylko po osobnej zgodzie i przydziale). Merge PR pozostaje decyzją człowieka.

**Data:** 2026-11-12 · **Gałąź:** `map-app-implementation` (baza `a81d22d`) · **Orkiestrator:** Claude Code, Opus 5.5
**Tracker statusu:** [docs/plan.md](../plan.md) — kroki 1–9 tam odhaczamy; ten plik opisuje *jak* je wykonać agentami.
**Źródła wymagań:** [PRD](../PRD.md) §6, [ADR-000](../ADR/000-main-architecture.md), [ADR-001](../ADR/001-dane-normalizacja-dopasowanie.md), [ADR-002](../ADR/002-odczyt-zdjec-modelami.md), [ADR-003](../ADR/003-raport-i-dashboard.md), [ADR-004](../ADR/004-databricks-cli-dla-agentow.md), [profil danych](../../reports/map-qa/profile.md), [AGENTS.md](../../AGENTS.md).

---

## 1. Stan wyjściowy (zweryfikowany 2026-11-12)

| Element | Stan | Jak sprawdzono |
|---|---|---|
| `app/` | Tylko `README.md` (ogólny checklist kursu, nie dotyczy Pythona). Brak `pyproject.toml`, kodu, testów, entry pointów | `ls app` |
| Komendy aplikacji | **Nie istnieją.** Docelowe z ADR-000 §6: `uv run map-qa check --stage {1,2}`, `uv run map-qa compare-counts`, `uv run pytest` (z `app/`) | ADR-000 §6, TAC-01/02 |
| Dane wejściowe | 8/8 plików zgodnych z `sources.json`; `signs` 119/119; liczności 99 768 / 85 405 / 561 / 561; Databricks zgodny | krok 0c, commit `a275ecb` |
| Narzędzia | uv 0.13.7, Python 3.12.16, node 24.22.1, npx 11.19.1, `codex-cli 0.167.2`, `opencode 2.2.5`, `gh 2.103.3`; **brak** `playwright-cli` w PATH | `--version` |
| Wytyczne wizualne | **Brak** `docs/design-guidelines.md` i `assets/design-tokens.json` | `ls` |
| Working tree | Czysty, gałąź zsynchronizowana z `origin` | `git status -sb` |
| Baseline testów | Brak testów → brak baseline failure; pierwszy test powstaje w T1.1 | — |

## 2. Polityka agentów, modeli i budżetu

| Rola | Narzędzie / model | Do czego | Mechanizm |
|---|---|---|---|
| Orkiestrator | Claude Code, Opus 5.5 | Decyzje architektoniczne, kontrakty współdzielone, briefy, integracja `cli`, akceptacja, Git | sesja główna |
| Worker domyślny | Claude Code subagent, **Haiku 5.5** | Testy i ograniczone moduły z jasnym kontraktem | narzędzie Agent (`model: haiku`), ad hoc, w tle |
| Worker trudniejszy | Codex, **`gpt-6.1-sol`** | Moduły z subtelną logiką (CRS/kierunki, kaskada vision), code review | `codex exec` (headless) |
| Worker prosty / research | Codex, **`gpt-6-luna`** | Proste moduły, sprawdzanie API w Context7/`--help` | `codex exec` |
| Worker alternatywny | OpenCode, **`xiaomi-token-plan-ams/mimo-v2.6-flash`** (Xiaomi Token Plan) | Szablony, proste testy, dokumentacja techniczna | `opencode run` (headless) |
| Review i akceptacja | Orkiestrator + `codex exec review` (Sol) + **człowiek** | Każdy milestone i finał | — |

**Budżet (ograniczenie):** workerzy wyłącznie w ramach abonamentów (Claude, ChatGPT/Codex, Xiaomi Token Plan). **Nie używać** `openrouter/xiaomi/*` (płatne per token). **Zero żądań OpenRouter** poza T6 (wymaga zgody i przydziału, [plan.md „Ochrona kosztu”](../plan.md#ochrona-kosztu-obowiązuje-cały-plan)). Copilot poza pulą (decyzja użytkownika 2026-11-12).

**Eskalacja:** worker nie dowozi Green po 2 próbach z poprawionym briefem, albo raportuje sprzeczność w kontrakcie → zadanie przechodzi o stopień wyżej (Haiku/MiMo/Luna → Sol → orkiestrator). Każda eskalacja = wpis w trackerze z powodem.

**Role:** domyślnie subagenty ad hoc z briefem; **bez** nowych plików ról w `.claude/agents/`. Wyjątek do rozważenia po milestone A: jeśli rola „test-writer” powtarza się ≥ 3 razy z tym samym zestawem narzędzi, zdefiniować ją krótko.

## 3. Delegowanie headless — instrukcja (zweryfikowana z `--help` zainstalowanych wersji)

Zasady wspólne: **jeden checkout**, workerzy edytują tylko pliki z kolumny „Editable files”, **nie wykonują żadnych zapisów Git** (add/commit/checkout/switch/stash/push) i zwracają raport + diff. Brief = `.agent-briefs/<task>.md`, wynik = `.agent-briefs/out/<task>.md`. Orkiestrator czyta `git diff`, powtarza testy i dopiero wtedy commituje.

### Codex (`codex exec`)
```bash
# implementacja / testy (Luna lub Sol), brief ze stdin, ostatnia wiadomość do pliku
codex exec -m gpt-6-luna -s workspace-write -C "D:/jsystems-claude-codex-gis-2026-11" \
  -c approval_policy='"never"' -c model_reasoning_effort='"medium"' \
  -o .agent-briefs/out/T2.2.md - < .agent-briefs/T2.2.md

# review milestone'u (Sol) względem bazy
codex exec review -m gpt-6.1-sol --base main --title "Milestone A review"
```
- `-s workspace-write`: zapis tylko w katalogu roboczym; `approval_policy="never"` odrzuca akcje wymagające zgody zamiast wisieć. Reguły `.codex/rules/course.rules` (np. `rm`, `env`, force-push = forbidden) obowiązują dalej.
- `--json` daje strumień zdarzeń do logu, `--output-schema <plik>` wymusza ustrukturyzowany raport (opcjonalnie).
- **Do sprawdzenia w T0.2:** czy sandbox `workspace-write` blokuje zapis do `.git/` (jeśli nie — zakaz Git tylko w briefie + kontrola `git log` po każdym workerze).

### OpenCode (`opencode run`)
```bash
opencode run -m xiaomi-token-plan-ams/mimo-v2.6-flash --title T4.2 \
  -f .agent-briefs/T4.2.md --format json \
  "Wykonaj brief z załączonego pliku. Zapisz raport do .agent-briefs/out/T4.2.md." \
  > .agent-briefs/out/T4.2.jsonl
```
- `--auto` zatwierdza wszystko, czego jawnie nie zabroniono — używać **tylko** po dodaniu projektowego `opencode.json` z regułami `deny` dla `git commit/add/push/checkout/reset`, `rm`, `env`, sieci (T0.1).
- Bez `--auto` zachowanie przy pytaniu o zgodę w trybie headless trzeba sprawdzić w T0.2.

### Claude Code subagent (Haiku 5.5)
Narzędzie Agent: `model: "haiku"`, `run_in_background: true`, prompt = treść briefu + „nie wykonuj zapisów Git; zwróć listę zmienionych plików i wynik testów”. Ten harness obsługuje subagenty (zweryfikowane: narzędzie Agent dostępne w sesji).

### Windows / Git Bash
Ścieżki API i argumenty zaczynające się od `/` przekazywać z `MSYS_NO_PATHCONV=1` (patrz commit `a81d22d`, ADR-004). Polecenia aplikacji uruchamiać z `app/`.

## 4. Bramki (hard stops) — także dla trybu „buduj bez zatrzymywania”

| Bramka | Kiedy | Dlaczego | W trybie autonomicznym |
|---|---|---|---|
| G-PAID | przed T6 | Płatne OpenRouter: zgoda na manifest + budżet ([plan.md §6](../plan.md#6-próba-z-przydziałem)) | **Pominąć T6**, kontynuować T7–T8; AC-19–AC-23 na realnym API zostają niezweryfikowane i trafiają do raportu końcowego |
| G-DESIGN | przed T8.3 | Brak referencji wizualnej (AGENTS.md Manual QA pkt 5) | Użyć domyślnego motywu Streamlit + polskie teksty; zgodność wizualna oznaczona jako niezweryfikowana |
| G-PUB | push / PR | Publikacja wymaga zgody | Push i PR tylko jeśli cel wprost na to pozwala; zawsze `origin` (fork), nigdy `upstream` |
| G-ARCH | sprzeczność PRD/ADR | Architektura nie może być wymyślona w planie | Zatrzymać dotknięty wątek, zapisać **proponowany ADR** w `docs/ADR/`, kontynuować niezależne zadania |

## 5. Macierz zależności (jedyna autorytatywna)

Kolumna „Owner/model”: **O** = orkiestrator (Opus 5.5), **H** = Claude subagent Haiku 5.5, **CS** = Codex `gpt-6.1-sol`, **CL** = Codex `gpt-6-luna`, **OC** = OpenCode MiMo-V2.6-Flash. Ścieżki plików względem `app/`, o ile nie podano inaczej. Commit wykonuje zawsze O, w formacie `Area: summary`.

| Task | Observable outcome | PRD/ADR links | Prerequisites | Owner/model | Editable files | Verification and handoff |
|---|---|---|---|---|---|---|
| **T0.1** Guardrails workerów | Projektowy `opencode.json` z deny dla Git/rm/env; `.agent-briefs/` z README formatu briefu | AGENTS.md „Commit Rules”, ADR-004 D-404 | — | O | `opencode.json`, `.agent-briefs/README.md` | Przegląd reguł; commit `Config: OpenCode permissions and brief folder` |
| **T0.2** Smoke test headless | Każdy worker (CL, CS, OC, H) wykonuje brief „utwórz `.agent-briefs/out/smoke-<x>.md` z wersją Pythona” i **nie** potrafi zrobić `git commit` | §3 tego planu | T0.1 | O (uruchamia), CL/CS/OC/H | `.agent-briefs/out/smoke-*.md` | Plik powstał; `git log` bez nowych commitów; wynik zapisany w §3. Brak commita (artefakty tymczasowe usunąć ręcznie przez człowieka lub zostawić w ignorowanym `out/`) |
| **T1.1** Szkielet uv + kontrakt pakietu | `uv run python -c "import map_qa"` działa; `uv run pytest` zbiera 0 testów bez błędu | ADR-000 §3 „Struktura”, §2 (wersje), TAC-05 | T0.2 | O (lockfile = hotspot) | `pyproject.toml`, `uv.lock`, `.python-version`, `src/map_qa/__init__.py`, `tests/conftest.py`, `config/thresholds.toml` (szkic) | Import OK; pytest „no tests ran” z kodem 5 udokumentowany; commit `App: uv scaffold` |
| **T1.2** Red: integralność i liczności | Testy padają z `ImportError/AttributeError` na brak `ingest`/`cli`, nie z błędu składni | PRD AC-01, AC-02, AC-03; ADR-001 §3.1, §8 | T1.1 | H | `tests/integration/test_ingest.py`, `tests/integration/test_cli_exit_codes.py` | O uruchamia pytest i potwierdza powód Red |
| **T1.3** Green: `config`, `ingest`, `cli check` (bez kandydatów) | `uv run map-qa check --stage 1` → kod 0, liczności 99 768 / 85 405 / 561; zmieniony bajt → kod 1 z nazwą pliku | AC-01–AC-03; ADR-000 §6 „CLI”; ADR-001 §3.1, §5 | T1.2 | CL | `src/map_qa/config.py`, `ingest.py`, `cli.py` | Testy T1.2 zielone; realny CLI na danych; ręczna kontrola hasha 1 pliku; commit `App: input integrity and counts` |
| **T1.4** Fixtures prawdziwych wierszy | Kopie wybranych wierszy (OSM z `maxspeed:*`, Overture z ≥ 2 regułami i `when`, zdjęcia z flagami) | ADR-000 §3 (`tests/fixtures/rows/`), ADR-001 §8 | T1.3 | O (współdzielone przez T2/T3) | `tests/fixtures/rows/*` | Każdy fixture z komentarzem źródła (plik, ID); commit `Test: real data row fixtures` |
| **T2.1** Red: normalizacja | Testy tabel ADR-001 §4.1–4.3 padają na brak `normalize` | AC-12; ADR-001 §4.1–4.3, §8; TAC-001-01, TAC-001-04 | T1.4 | H | `tests/unit/test_normalize.py` | O potwierdza Red; **równolegle z T3.1** (rozłączne pliki — worker o tym poinformowany) |
| **T2.2** Green: `normalize` | Surowe `maxspeed_raw`/`speed_limits_raw` zachowane bajt w bajt; `PL:*` w `maxspeed:type` informacyjnie | jw.; profil „5 faktów” pkt 2–3 | T2.1 | CL (równolegle z T3.2) | `src/map_qa/normalize.py` | Testy zielone; O powtarza; commit `App: normalize maxspeed, speed_limits and surface` |
| **T3.1** Red: CRS i ocena połączeń | 6 przypadków z [plan.md §3](../plan.md#3-crs-i-ocena-połączeń) padają | AC-04, AC-06–AC-09; ADR-001 §3.2–3.4, D-101, D-103; TAC-001-02 | T1.4 | H (równolegle z T2.1) | `tests/unit/test_matching.py`, `tests/integration/test_matching_data.py` | O potwierdza Red |
| **T3.2** Green: `matching` | Pełne dane: 3 zdjęcia bez kandydata, ≥ 65 `ambiguous_link`; suma = 561 | jw.; TAC-001-03 | T3.1 | **CS** (kierunki, zawijanie 360°, remisy) | `src/map_qa/matching.py` | Testy zielone; ręcznie jedno zdjęcie z niepewnym połączeniem (otwarte z `offline/`); commit `App: CRS 2180 and photo-road link assessment` |
| **T4.1** Red: `compare` | Testy kategorii z ADR-001 §8 padają | AC-10–AC-13, AC-10a, AC-16; ADR-001 §3.5, §4.5, D-102 | T2.2, T3.2 | H | `tests/unit/test_compare.py` | O potwierdza Red |
| **T4.2** Green: `compare` | Każda para ma 1 kategorię; niepewne połączenie nigdy `rozbieżne` | jw.; AC-07 | T4.1 | CL | `src/map_qa/compare.py` | Testy zielone; commit `App: candidate categories` |
| **T4.3** Red+Green: `report` (MD/HTML/CSV) | 3 formaty, ta sama liczba kandydatów, autoescape HTML, atrybucja | AC-14, AC-15, AC-24–AC-26; ADR-003 §3.1, §4, D-301; TAC-003-01 | T4.2 (kontrakt wyjścia ADR-001 §4.5) | OC (szablony) — testy najpierw w tym samym zadaniu, Red pokazany w raporcie | `src/map_qa/report.py`, `src/map_qa/templates/*`, `tests/unit/test_report.py` | O powtarza Red→Green z historii; commit `App: Markdown/HTML/CSV report` |
| **T4.4** `sources_remote` + `compare-counts` | Bez zmiennych → kod 0 i wpis „Ograniczenia”; ze zmiennymi → 5 liczności | AC-05; ADR-000 §6 `compare-counts`, D-02 | T1.3 | CL (równolegle z T4.1–T4.3) | `src/map_qa/sources_remote.py`, `tests/unit/test_sources_remote.py` | Test bez sieci (transport testowy); 1 realne wywołanie tylko jeśli zmienne ustawione; commit `App: optional Databricks counts` |
| **T4.5** Integracja etapu 1 w `cli` | `uv run map-qa check --stage 1` tworzy raport w `reports/map-qa/runs/<run_id>/`; 0 żądań sieciowych; ≤ 5 min | AC-21, AC-31 (bez vision); TAC-01–TAC-04 | T4.3, T4.4 | O | `src/map_qa/cli.py`, `tests/e2e/test_stage1_cli.py` | Pełny pytest (liczby zebranych/przeszłych/pominiętych); realny CLI; **Manual QA**: 1 kandydat `rozbieżne` odtworzony ręcznie z wejść; `git status` wejść czysty; commit `App: stage 1 end-to-end without models` |
| **R-A** Review milestone A | Lista uwag i niespełnionych AC dla etapu 1 bez modeli | AC-01–AC-16, AC-24–AC-26 | T4.5 | CS (`codex exec review --base main`) + O | — (uwagi do `.agent-briefs/out/R-A.md`) | O klasyfikuje uwagi; poprawki jako osobne zadania T4.x-fix |
| **T5.1** Kontrakt `store` (SQLite) | Schemat: decyzje, cache, budżet, runy; migracja idempotentna | ADR-000 §5.2, D-05; ADR-003 §3.2, D-303; ADR-002 §4.8–4.9 | T4.5 | O (kontrakt współdzielony przez vision i dashboard) | `src/map_qa/store.py`, `tests/unit/test_store.py` | Red→Green; commit `App: SQLite store` |
| **T5.2** Weryfikacja SDK `openrouter==1.3.107` | Zapis w ADR-002 §2: retry `none`, `timeout_ms` w `decisions.create`, argumenty klienta | ADR-002 §2 „Do potwierdzenia”, ADR-000 D-03; plan.md Ryzyka | T1.1 | CL (research: Context7 → kod SDK) | `docs/ADR/002-odczyt-zdjec-modelami.md` §2 (tylko tabela) | O weryfikuje źródła; brak timeoutu → G-ARCH: proponowany ADR dla surowego POST |
| **T5.3** Red: `vision` (transport testowy) | Testy budżetu, limitu 0, cache, abstencji, treści `state`, wyłączenia modelu po błędzie | AC-17–AC-20f, AC-22; ADR-002 §3–4, §8, D-201–D-204; TAC-002-01/02 | T5.1, T5.2 | H | `tests/unit/test_vision_*.py`, `tests/integration/test_vision_cascade.py` | Testy zależne od kształtu odpowiedzi API **pominięte z powodem „brak capture”** (ADR-002 §4.5); O potwierdza Red |
| **T5.4** Green: `vision` | Domyślnie 0 żądań; `--decision-limit 2 --max-cost-usd 0` → kod 2 | jw. | T5.3 | **CS** | `src/map_qa/vision.py`, `config/thresholds.toml` | Testy zielone; realny CLI bez limitów → 0 żądań, brak manifestu; commit `App: vision cascade, budget and cache (no paid calls)` |
| **T5.5** `evaluation` | Trafność i pokrycie tylko na `certain`, podział po `sequence` | AC-23; ADR-002 §4.10 | T5.1 (równolegle z T5.3–T5.4) | CL | `src/map_qa/evaluation.py`, `tests/unit/test_evaluation.py` | Red→Green; commit `App: reading evaluation` |
| **T5.6** Integracja vision w `cli` + raport | Raport pokazuje stopień odczytu i `model_unavailable` | AC-20e, AC-20f, AC-21 | T5.4, T5.5 | O | `src/map_qa/cli.py`, `src/map_qa/templates/*` (sekcja vision) | Pełny pytest + realny CLI; commit `App: vision results in report` |
| **T6** Próba płatna z przydziałem | Capture → mocki z capture → odblokowane testy; raport kosztu | AC-19–AC-23 na realnym API; ADR-002 §4.5, §4.7 | T5.6 + **G-PAID** | O | `tests/fixtures/captures/*`, testy odblokowane | Wg [plan.md §6](../plan.md#6-próba-z-przydziałem); **pomijane w trybie autonomicznym** |
| **T7.1** Red: etap 2 (oświetlenie, skrzyżowanie) | Testy `lit`, topologii `node_ids`, most/tunel/granica → `not_comparable` | AC-32; ADR-001 §4.4 | T4.5, T5.6 | H | `tests/unit/test_stage2_*.py` | O potwierdza Red |
| **T7.2** Green: etap 2 | `uv run map-qa check --stage 2` → kod 0; `questions_version` 2 | jw.; ADR-002 §4.1 | T7.1 | CL (normalize/compare) — **serialnie**, bo edytuje pliki z T2/T4 | `src/map_qa/normalize.py`, `compare.py`, `config/thresholds.toml` | Testy zielone; ręcznie 1 węzeł skrzyżowania; commit `App: lighting and junction checks` |
| **T8.1** Decyzja wizualna | `docs/design-guidelines.md` albo zapis „domyślny motyw Streamlit” | AGENTS.md Manual QA pkt 5; **G-DESIGN** | — | Człowiek / O | `docs/design-guidelines.md` | Zgoda użytkownika lub wpis o pominięciu |
| **T8.2** Red: dashboard (logika + E2E) | Testy filtrów, zapisu decyzji, zakładki „Do poprawy”, braku żądań zewnętrznych | AC-27–AC-30; ADR-003 §3.2–3.3, §8; TAC-003-02/03 | T5.1, T4.5 (równolegle z T7.x — rozłączne pliki) | H | `tests/unit/test_dashboard_logic.py`, `tests/e2e/test_dashboard.*` | O potwierdza Red; weryfikacja dostępności Playwright CLI (`npx @playwright/cli --help`) |
| **T8.3** Green: dashboard Streamlit | Działający `streamlit run dashboard/app.py`, polskie teksty | jw.; ADR-000 D-06, ADR-003 D-302 | T8.1, T8.2 | OC | `dashboard/app.py`, `.streamlit/config.toml` | Testy zielone; **Manual QA Playwright**: zrzuty obu zakładek, restart serwera i trwałość decyzji, konsola bez błędów; commit `App: Streamlit review dashboard` |
| **R-F** Review końcowy | Lista niespełnionych AC 01–33 i TAC; raport z tym, czego nie zweryfikowano (np. T6) | AC-31–AC-33 | T7.2, T8.3 (T6 opcjonalnie) | CS (`codex exec review --base main`) + świeża sesja Claude bez kontekstu implementacji + **człowiek** | — | Uwagi → zadania fix; potem G-PUB |
| **T9** Pull request | PR `map-app-implementation` → `main` w `origin` (fork) | — | R-F + **G-PUB** | O | — | `gh pr create -R marciniaklukasz/jsystems-claude-codex-gis-2026-11 --base main`; opis z listą AC i dowodami |

## 6. Ścieżka krytyczna i równoległość

**Ścieżka krytyczna:** T0.1 → T0.2 → T1.1 → T1.2 → T1.3 → T1.4 → T3.1 → T3.2 → T4.1 → T4.2 → T4.3 → T4.5 → T5.1 → T5.3 → T5.4 → T5.6 → T7.1 → T7.2 → R-F → T9.
(T3 jest na ścieżce zamiast T2, bo `matching` jest trudniejszy i przydzielony Sol.)

**Okna równoległe (rozłączne pliki, jeden checkout, bez worktree):**
- T2.1‖T3.1, potem T2.2‖T3.2.
- T4.4 równolegle z T4.1–T4.3.
- T5.2 (research) od razu po T1.1; T5.5 równolegle z T5.3–T5.4.
- T8.1–T8.3 równolegle z T7.x po T5.1.

Każdy brief zawiera sekcję „Równolegle pracują: …, nie dotykaj ich plików”.

## 7. Hotspoty współdzielonych plików (tylko orkiestrator, serialnie)

`app/pyproject.toml`, `app/uv.lock` (każda nowa zależność przez O) · `src/map_qa/cli.py` (integracja T4.5, T5.6) · `tests/conftest.py`, `tests/fixtures/rows/` · `config/thresholds.toml` (T5.4, T7.2 — serialnie) · `src/map_qa/store.py` (kontrakt dla vision i dashboardu) · `src/map_qa/templates/` (T4.3, potem T5.6) · `docs/plan.md` (tracker) i `docs/ADR/*`.

## 8. Awarie, rollback i plan awaryjny

- **Worker zepsuł zakres** (pliki spoza listy): `git diff --stat` przed integracją; zmiany spoza listy odrzucane (`git restore <plik>` przez O), brief poprawiony.
- **Czerwone testy po integracji:** brak commita; O cofa do ostatniego commita zadania (`git restore` dla zmienionych plików zadania), zadanie wraca z logiem błędu.
- **Commit wadliwy już w historii:** `git revert <sha>` (bez przepisywania historii wypchniętej na `origin`).
- **Worker/model niedostępny lub limit planu wyczerpany:** to samo zadanie przechodzi na kolejnego workera z tym samym briefem (OC ↔ CL ↔ H); w ostateczności O wykonuje matrycę sekwencyjnie sam.
- **Mniejszy fallback (brak czasu/narzędzi):** dowieźć **milestone A** (T0–T4.5 + R-A): etap 1 bez modeli, raport MD/HTML/CSV — demonstrowalny i spełniający AC-01–AC-16, AC-21, AC-24–AC-26. Kolejny poziom: T5 bez T6, potem T8, na końcu T7.

## 9. Tryb „buduj całą aplikację bez zatrzymywania”

Gdy użytkownik ustawi taki cel, obowiązuje ta sama macierz, z różnicami:
1. Orkiestrator nie czeka na przegląd po każdym zadaniu, ale **nie omija** Red→Green, weryfikacji ani bramek z §4.
2. Briefy kompilowane tuż przed wysłaniem do `.agent-briefs/<task>.md` (commitowane razem z wynikiem zadania).
3. Po każdym milestone (A: T4.5, B: T5.6, C: T7.2, D: T8.3) wpis statusu w [docs/plan.md](../plan.md) i krótkie podsumowanie w rozmowie.
4. G-PAID → pominięcie T6; G-DESIGN → domyślny motyw; G-PUB → tylko gdy cel wprost zezwala; G-ARCH → proponowany ADR i kontynuacja niezależnych wątków.
5. Koniec = R-F z jawną listą tego, co zweryfikowano, a czego nie.

## 10. Format briefu (`.agent-briefs/<task>.md`)

1. Cel i obserwowalny wynik (z macierzy). 2. Wycinki kontraktów (fragmenty PRD/ADR z linkami — worker nie odkrywa architektury sam). 3. Wyniki poprzedników (sygnatury, ścieżki, fixtures). 4. **Editable files** — zamknięta lista. 5. Równolegle pracują: … 6. Kroki: Red (pokaż powód porażki) → Green → Refactor. 7. Dane testowe i oczekiwane wartości. 8. Komendy weryfikacji (z `app/`): `uv run pytest <ścieżki> -q`, `uv run map-qa …`. 9. Zakazy: Git write, zmiana zakresu, sieć/płatne API, czytanie sekretów. 10. Raport: zmienione pliki, wynik testów (zebrane/przeszłe/pominięte), sprzeczności.

## 11. Nierozstrzygnięte decyzje

1. ~~Referencja wizualna dashboardu~~ — **rozstrzygnięte 2026-11-12:** domyślny motyw Streamlit.
2. ~~Publikacja w trybie autonomicznym~~ — **rozstrzygnięte:** push na `origin` po każdym milestone.
3. ~~Granulacja PR~~ — **rozstrzygnięte:** PR na milestone (A–D), do `main` w `origin`; PR kolejnego milestone'u bazuje na gałęzi poprzedniego, merge robi człowiek.
4. Sprawdzenie w T0.2, czy sandbox Codex `workspace-write` chroni `.git/` i jak `opencode run` bez `--auto` reaguje na pytanie o zgodę.

## 12. Pierwsze ograniczone zadanie i bramka review

- **Pierwsze zadanie po autoryzacji:** **T0.1** — `opencode.json` z regułami deny i `.agent-briefs/README.md`; potem T0.2 smoke test czterech workerów.
- **Bramka review tego planu:** użytkownik akceptuje macierz, politykę modeli, bramki i odpowiada na decyzje z §11. Do tego czasu żadne zadanie z macierzy nie jest uruchamiane.
