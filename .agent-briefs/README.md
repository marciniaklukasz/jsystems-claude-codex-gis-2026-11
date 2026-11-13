# Briefy workerów (plan orkiestracji §3, §10)

Folder z briefami dla workerów headless (Codex `codex exec`, OpenCode `opencode run`, subagent Claude Haiku). Briefy (`<task>.md`) są commitowane; wyniki (`out/<task>.md`) są ignorowane w Git.

## Format briefu `<task>.md`

1. Cel i obserwowalny wynik (z macierzy planu §5).
2. Wycinki kontraktów (fragmenty PRD/ADR z linkami — worker nie odkrywa architektury sam).
3. Wyniki poprzedników (sygnatury, ścieżki, fixtures).
4. **Editable files** — zamknięta lista; nic poza nią.
5. Równolegle pracują: … — nie dotykaj ich plików.
6. Kroki: Red (pokaż powód porażki) → Green → Refactor.
7. Dane testowe i oczekiwane wartości.
8. Komendy weryfikacji (z `app/`): `uv run pytest <ścieżki> -q`, `uv run map-qa …`.
9. Zakazy: zapisy Git (add/commit/checkout/switch/stash/push/restore), zmiana zakresu, sieć i płatne API, czytanie sekretów i `.env`.
10. Raport do `out/<task>.md`: zmienione pliki, wynik testów (zebrane/przeszłe/pominięte), sprzeczności w kontrakcie.

## Guardraile

- OpenCode: projektowy [`opencode.json`](../opencode.json) — deny dla zapisów Git, `rm`, `env`, sieci; `ask` dla reszty (w trybie headless bez `--auto` pytanie = odmowa).
- Codex: `-s workspace-write`, `approval_policy="never"`, reguły `.codex/rules/course.rules`.
- Claude subagent: zakaz Git w briefie + kontrola `git log -1` i `git reflog -5` przez orkiestratora po zadaniu.
- Orkiestrator przed integracją: `git status --short`, `git diff --stat`; zmiany spoza „Editable files” są odrzucane.
