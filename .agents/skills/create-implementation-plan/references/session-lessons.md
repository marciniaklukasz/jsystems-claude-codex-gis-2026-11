# Wnioski z sesji źródłowych

To uzasadnienie zasad skilla, nie specyfikacja kolejnej aplikacji. Czytaj przy analizie historii lub zmianie instrukcji.

## Źródła i ograniczenia

- Tworzenie planu: Claude `cfff1a28-a5c4-4d2f-82a8-c37e3ac63605`, 2026-11-12.
- Wykonanie: `966565f7-658d-4976-9897-81093e86756e`, 2026-11-12–13. Sesja zaczyna się od wdrażania istniejącego planu.
- Artefakt: `docs/plans/map-qa-full-app-implementation-plan.md`; pierwszy commit `63974fe`, poprawki audytu `8d8d866`, dalsze ustalenia `c01f0f0`. To historyczne identyfikatory, nie zależności skilla.

Ustalenia oparto na lokalnych zapisach wiadomości, wywołaniach narzędzi, raporcie audytu i historii planu. Deklaracja ukończenia przez agenta nie dowodzi poprawności. Nie kopiowano całych logów ani sekretów. Nie wszystkie ustalenia pierwotnego audytu zweryfikowano ponownie oddzielnie.

## Odtworzony proces

1. Pierwotny prompt proponował jeden demonstracyjny fragment. Użytkownik rozszerzył zakres na całą aplikację z fazami i późniejszym wykonaniem autonomicznym.
2. Agent zbadał checkout, PRD, ADR, profil danych i lokalną pomoc narzędzi. Potwierdził pusty scaffold, brak testów, narzędzia QA w PATH i referencji wizualnej.
3. Powstał draft: macierz, właściciele plików, ścieżka krytyczna, milestone'y, bramki zgód, fallback i briefy. Użytkownik wybrał motyw, zasady publikacji i PR.
4. Dopiero po drafcie zlecono niezależny audyt. Raport zgłosił 3 problemy blokujące, 15 ważnych i 13 drobnych. Orkiestrator opisał samodzielne sprawdzenie pięciu kluczowych tez. To liczności raportu, nie dowód wszystkich punktów.
5. Użytkownik zatwierdził P1–P7. Subagent poprawiał dokumenty, a orkiestrator kontrolował diff i integrował wynik. Wymagania poprawiono u źródła, nie tylko w planie.
6. Dalsze decyzje o endpointach, modelach, capture i budżecie zmieniły zależności. Następna sesja wdrażała plan; smoke testy ujawniły ograniczenia wymagające zastępstw.

## Problemy i zabezpieczenia

| Obserwacja | Znaczenie i granica pewności | Zabezpieczenie |
|---|---|---|
| Podane ID wskazywało wykonanie, nie tworzenie planu | Potwierdza to początek sesji | Najpierw ustal źródło i moment powstania artefaktu |
| Audyt po drafcie znalazł sprzeczności dokumentów | Potwierdzony raport, nie każdy punkt osobno | Niezależny audyt przed draftem, weryfikacja ustaleń przez orkiestratora |
| Tekst i diagram inaczej klasyfikowały brak dowodu | P1 rozstrzygała regułę wpływającą na wyniki | Audyt kolejności reguł, braków danych i diagramów |
| Niepewność zdjęcia mieszała się z dowodem mapowym | P2 określała zakres wpływu niepewności | Reguła powiązana ze źródłem dowodu i przypadkami testowymi |
| Ścieżki CLI i dashboardu nie miały wspólnej bazy | Ryzyko różnych katalogów wynikowych w audycie | Jawny katalog roboczy i baza ścieżek |
| Opis hotspotów kłócił się z macierzą | Poprawiano właścicieli i dodano zadanie integracji | Jedna macierz, jeden właściciel pliku w danym momencie |
| Workerzy działali inaczej niż zakładano | Zapis: OpenCode milczał ponad 10 min, Codex nie mógł zapisać cache | Smoke test, limit bezczynności, dozwolony cache i zastępstwa |
| Worker próbował commitować mimo zakazu | Widać próbę i blokadę narzędzia; brief nie egzekwuje uprawnień | Oddziel zakaz, blokadę techniczną i kontrolę Git |
| Orkiestrator przejmował część zadań | Widać odstępstwa przy testach i modułach, ale także rzeczywiste delegowanie. Brak podstaw do twierdzenia, że całkowicie zrezygnował z agentów | Wiążący przydział i uzgodnione zastępstwa, inaczej pytanie |
| Capture dodano jako osobną zależność przed mockami | Zmiana zasad testowania zmieniła ścieżkę krytyczną | Ustal capture przed mockiem; nie wymyślaj odpowiedzi |
| Sukces zadeklarowano przed pełnym retestem po poprawce | Agent później sam przyznał brak pełnego przebiegu | Dowody dla końcowego stanu, bez sumowania starego przebiegu i retestu |
| Hook wielokrotnie kwestionował koniec, interpretacja progów się zmieniała | Spór o kryteria i brak zgody na część merge | Uzgodniona DoD; osobne statusy kodu, jakości danych i merge |
| Trafność skrzyżowań raportowano na jednej parze testowej po zmianie etykiet | Jawnie mała próba; nie dowodzi generalizacji ani celowego manipulowania | Minimalne dowody i ograniczenia; decyzja, wersja i zasady przed nową próbą |
| Zapis kończy błąd dostępu 403 | Nie potwierdza wyniku trwającej weryfikacji | Przerwanie to brak dowodu, nie sukces |

## Co powtarzać

- Rozpoznanie rzeczywistego repo i pomocy zainstalowanych CLI.
- Małe zadania z wynikiem, wymaganiem, zakresem plików i dowodem.
- Niezależny audyt, decyzje użytkownika, poprawki u źródła i kontrola diffu.
- Brief tuż przed delegacją, ograniczony kontekst i wykorzystanie tego samego wykonawcy przy uzgodnionych poprawkach.
- Testy przed zmianą zachowania, realny runtime i odtworzenie wybranego wyniku z wejść.
- Jawne koszty, ograniczenia i statusy niezweryfikowane; zachowanie surowych danych.

Użytkownik dodatkowo ustalił: pytania pojedynczo z rekomendacją, wybór wariantu dla każdego nowego planu, dwa szablony, wiążący przydział i zastępstwa, niezależny audyt przed draftem i po istotnych zmianach, akceptację przed wykonaniem. To świadome wymagania skilla, nie fakty o każdym projekcie.
