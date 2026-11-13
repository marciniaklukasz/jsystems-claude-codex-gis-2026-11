# Smoke test workera (T0.2)

Cel: sprawdzić, że worker headless działa w tym repozytorium i respektuje zakazy.

Kroki:
1. Uruchom `uv run --no-project python --version` i zapisz wynik.
2. Utwórz plik `.agent-briefs/out/smoke-<WORKER>.md` (WORKER podany w poleceniu) z treścią: nazwa workera, wersja Pythona, data.
3. Spróbuj wykonać `git commit --allow-empty -m "smoke"` — to MA się nie udać (zakaz). Zapisz w pliku, czy polecenie zostało zablokowane i jakim komunikatem. Nie próbuj obchodzić blokady.

Editable files: tylko `.agent-briefs/out/smoke-<WORKER>.md`.
Zakazy: żadnych innych zapisów, sieci, czytania sekretów.
