# Plan implementacji: {cel}

**Status:** DRAFT — do przeglądu użytkownika; wykonanie czeka na akceptację.
**Data / checkout / baza:** {wartości}
**Wariant delegowania:** {native-only albo headless-cli; wybór użytkownika}
**Tracker wykonania:** {istniejący plik albo uzgodniona lokalizacja}

## Cel i źródła

{Obserwowalny wynik, zakres i wyłączenia, linki do właściwych AGENTS.md, wymagań, PRD, ADR i referencji wizualnej. Dla brakujących dokumentów uzgodnione minimum; nie wymyślaj architektury.}

## Stan wyjściowy

| Obszar | Potwierdzony stan | Źródło / wykonana kontrola | Ograniczenie |
|---|---|---|---|
| Kod i entry pointy | {stan} | {ścieżki} | {braki} |
| Git i cudze zmiany | {stan} | {kontrola} | {zakres do zachowania} |
| Build, testy, startup | {osobne wyniki albo nieuruchomione} | {komendy i katalog roboczy} | {baseline failures, skips} |
| Dane, API i fixtures | {stan} | {źródła bez sekretów} | {capture / zgody} |
| Narzędzia i modele | {wersje / mechanizmy} | {pomoc lokalna / stan harnessu} | {niesprawdzone zachowania} |

## Decyzje i granice uprawnień

{Uzgodnione wymagania, wariant delegacji, budżet i warunek zatrzymania, dozwolone środowiska. Osobno zgoda na wykonanie, publikację, PR i merge. Nie deklaruj nieudzielonej zgody. Pytania i blokady z rekomendacją.}

## Macierz zależności i odpowiedzialności

| Zadanie | Obserwowalny wynik | Wymagania / PRD / ADR | Zależności | Wykonawca / model | Dozwolone pliki | Weryfikacja i przekazanie |
|---|---|---|---|---|---|---|
| {ID} | {ograniczony wynik} | {konkretna sekcja} | {ID lub brak} | {agent, mechanizm, model gdy wybrany} | {zamknięty zakres} | {komenda, oczekiwany wynik, dowód, odbiorca, granica commita} |

{Realne zadania: Red przed Green, integracja po zależnych komponentach, manualne sprawdzenie runtime i niezależny review. Wyjątki dostosuj do dokumentacji lub refaktoryzacji. Opis faz nie tworzy drugiej listy zależności.}

## Współdzielone pliki i awarie

{Ścieżka krytyczna; konkretne zadania równoległe; jeden właściciel współdzielonego pliku w danym momencie. Warunki eskalacji, limit bezczynności i prób, zatwierdzone zastępstwa. Brak zastępstwa oznacza pytanie, bez przejęcia przez orkiestratora. Bezpieczne odtworzenie tylko własnych zmian zgodnie z uprawnieniami. Uzgodniony mniejszy zakres, jeśli potrzebny.}

## Briefy i odbiór

{Trwałe ścieżki briefów i raportów. Brief: cel, wycinki kontraktów, wyniki poprzedników, dozwolone pliki, prace równoległe, kroki, dane i wyniki, komendy i zakazy. Raport: pliki, diff, zaobserwowane wyniki i liczności, problemy, koszty. Odbiór: sprawdzenie diffu i powtórzenie kontroli przez orkiestratora przed integracją.}

## Dowody i definicja zakończenia

| Kryterium | Sprawdzenie | Dowód / ścieżka artefaktu | Status |
|---|---|---|---|
| {wymaganie} | {test lub ręczny scenariusz} | {planowana lokalizacja; nie udawaj istniejącego dowodu} | {przed wykonaniem: niezweryfikowane} |

{Osobne kontrole: build, testy z licznościami i skips, startup, manualne UI/CLI/API. Dla UI zrzuty i odniesienie do projektu wizualnego według instrukcji repo. Dla dokumentacji: treść, diff, linki. Niezależny recenzent i podstawa review; ponowienie odpowiednich kontroli po ostatniej zmianie. Ograniczenia danych oddzielnie od implementacji, publikacja i merge odrębnie.}

## Audyt i przekazanie użytkownikowi

| Waga | Źródła i sekcje / linie | Rozbieżność | Skutek | Rekomendacja | Decyzja / wynik ponownego audytu |
|---|---|---|---|---|---|
| {ustalenie albo brak ustaleń z zakresem kontroli} | {źródła} | {problem} | {skutek} | {propozycja} | {stan} |

{Identyfikacja niezależnego recenzenta, zakres audytu, potwierdzenie ustaleń przez orkiestratora, otwarte blokady. Pierwszy ograniczony krok po akceptacji. Prośba o dokładny review i akceptację. Bez rozpoczęcia realizacji.}
