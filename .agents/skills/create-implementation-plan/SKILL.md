---
name: create-implementation-plan
description: Przygotuj i poddaj audytowi plan implementacji aplikacji, funkcji, poprawki lub refaktoryzacji, z jawnym podziałem pracy między agentów. Używaj przy tworzeniu lub istotnej aktualizacji planu przed wykonaniem; samo planowanie nie uruchamia implementacji.
---

# Plan implementacji do akceptacji

Przygotuj plan po polsku, z angielskimi nazwami plików i identyfikatorami. Zachowaj istniejący projekt, zakres użytkownika i właściwe instrukcje repozytorium. Skill obsługuje nowe i istniejące aplikacje, bez narzucania stosu.

## Rozpoznanie i decyzje

1. Ustal cel, zakres i obserwowalny wynik. Przeczytaj właściwe AGENTS.md, także nadrzędne i zagnieżdżone, dostępne wymagania, odpowiednie PRD/ADR i uzgodnione referencje wizualne. Odróżnij instrukcje projektu od przykładów szkoleniowych. Nie przeszukuj zakazanych katalogów ani sekretów.
2. Sprawdź checkout, stan Git, kod, miejsca wywołań, deskryptory budowania, entry pointy i testy. Nie zastępuj istniejącej aplikacji scaffoldem. Zachowaj cudze zmiany. Podaj źródła komend i co rzeczywiście uruchomiono. Brak testów, nieuruchomiona komenda i istniejąca porażka to różne stany.
3. Istotne braki i sprzeczności rozstrzygaj z użytkownikiem, po sprawdzeniu dostępnych źródeł. Brak PRD/ADR sam w sobie nie blokuje prostego planu, chyba że instrukcje projektu ich wymagają. Zmiana uzgodnionego zachowania wymaga decyzji i aktualizacji źródła; brakująca architektura trafia do propozycji ADR. Nie zastępuj decyzji ukrytym założeniem.
4. Używaj interaktywnego narzędzia pytań, jeśli jest dostępne w bieżącym trybie; inaczej pytaj w rozmowie. **Jedno pytanie naraz, potem czekaj na odpowiedź.** Podaj 2–3 sensowne opcje, rekomendację z uzasadnieniem i możliwość własnej odpowiedzi. Nie powtarzaj uzgodnionych decyzji, nie wymagaj stałej liczby pytań i nie traktuj ciszy jako zgody. Kontynuuj niezależne rozpoznanie podczas oczekiwania.
5. Przy każdym nowym planie uzyskaj wybór wariantu: **native-only** (wbudowane subagenty) albo **headless-cli** (delegowanie między narzędziami). Jeśli użytkownik już wybrał wariant dla tego planu, nie pytaj ponownie. Sprawdź dostępność mechanizmu, modeli, uprawnień i ograniczeń kosztowych. Dostępność narzędzia nie oznacza zgody na płatne wywołania.

Bez dostępu do rzeczywistego repozytorium oznacz rezultat jako **szkic na podstawie opisu**, ze wskazaniem niepotwierdzonych komend, plików i kontraktów. Nie przedstawiaj go jako kompletnego, przeaudytowanego draftu; audyt źródeł pozostaje niewykonany.

Przy odtwarzaniu procesu z historii lub zmianie zasad przeczytaj [wnioski z sesji](references/session-lessons.md). Te sesje nie są wymagane przy kolejnych planach.

## Dwa szablony, wspólny kontrakt

Złóż plan z [części wspólnej](assets/plan-common.md) i **jednego** wariantu:

- [native-only](assets/plan-native.md): tylko natywne agenty i subagenty bieżącego harnessu;
- [headless-cli](assets/plan-headless.md): agenty różnych narzędzi przez CLI bez interakcji, opcjonalnie obok natywnych subagentów.

Wypełnij pola szablonu danymi projektu, usuń niepasujące instrukcje i połącz części w jeden dokument. Nie kopiuj pustych tabel. Linkuj do konkretnych sekcji wymagań i kontraktów zamiast powielać dokumenty. Używaj istniejącego trackera; jedna macierz pozostaje źródłem zależności i odpowiedzialności.

Macierz zawiera: zadanie, obserwowalny wynik, źródło wymagań, zależności, wykonawcę/model, dozwolone pliki, weryfikację i przekazanie. Każde zadanie ma granicę akceptacji i przypisanie do zweryfikowanego commita. Kilka zadań, np. Red i Green, może współdzielić commit po przejściu wymaganej weryfikacji; nie commituj samego czerwonego etapu. Uwzględnij integrację po zależnych komponentach, ścieżkę krytyczną, współdzielone pliki, rollback bez niszczenia cudzych zmian oraz mniejszy zakres awaryjny do uzgodnienia.

Planowanie nie upoważnia do implementacji, workerów implementacyjnych, kosztów, publikacji ani merge. Rozpoznanie i audyt mogą korzystać z uprawnionych agentów tylko do odczytu. Nie wykonuj płatnych lub niebezpiecznych prób jedynie dla sprawdzenia środowiska. Nieznane zachowania wpisz jako smoke test po akceptacji.

## Podział pracy jest wiążący

- Orkiestrator ustala kontrakty, przygotowuje briefy, koordynuje zależności, sprawdza diff i odtwarza kontrole przed integracją. Implementuje tylko zadania jawnie przypisane mu w macierzy.
- Wykonawca realizuje swój zakres, nie zmienia wymagań i nie akceptuje własnej pracy. Zapisów Git dokonuje tylko przy jawnie przydzielonej roli i zgodzie. Recenzent ocenia rezultat niezależnie.
- **Nie zastępuj delegowania samodzielną realizacją dla wygody lub oszczędności czasu.** Gdy wykonawca jest niedostępny lub nie dowozi, użyj wcześniej zaakceptowanego zastępstwa. Bez niego zgłoś problem, zapytaj o zmianę i kontynuuj tylko niezależne zadania. Zapisz powód i zgodę w trackerze. Zmiana narzędzia między wariantami też wymaga uzgodnienia.
- Ustal limit bezczynności i prób przed eskalacją. Zakaz w briefie nie dowodzi blokady technicznej; odróżnij deklarację, rzeczywistą blokadę i kontrolę po wykonaniu.
- Równolegle uruchamiaj wyłącznie zadania o niezależnych wejściach i rozłącznych plikach. Serializuj współdzielone kontrakty, lockfile i integrację. Worktree tylko zgodnie z instrukcjami i zgodą dla repozytorium.

## Audyt przed zapisaniem draftu

Przygotuj treść kandydata i zleć **niezależny audyt agentowi/subagentowi tylko do odczytu**, zgodnie z wybranym wariantem. Przekaż cel, kandydata i surowe źródła; nie sugeruj oczekiwanego werdyktu. Nieobecny recenzent uruchamia regułę zastępstw, a nie pominięcie audytu. Dozwolony jest tymczasowy materiał dla recenzenta; nie przedstawiaj go jako przeaudytowanego draftu.

Sprawdź między AGENTS.md, PRD, ADR i planem:

- pokrycie wymagań, kolejność reguł, kontrakty wejść/wyjść i zgodność tekstu z diagramami;
- limity, jednostki, wersje, ścieżki z katalogiem bazowym, flagi, kody wyjścia i formaty danych;
- zależności, właścicieli plików i zgodność macierzy z opisem faz;
- wykonalność komend, uprawnienia, koszt, zasady mocków, źródła fixtures i dostępność narzędzi;
- mierzalną definicję zakończenia, dowody, ograniczenia próbek oraz osobne decyzje publikacji i merge.

Raport: `waga | źródła i sekcje/linie | rozbieżność | skutek | rekomendacja | potrzebna decyzja`. Orkiestrator sprawdza ustalenia w źródłach. Popraw oczywiste błędy w dozwolonym zakresie. Zmiany wymagań lub architektury uzgodnij pytaniami. Po istotnej zmianie ponów niezależny audyt dotkniętego zakresu. Nie deklaruj spójności przy nierozstrzygniętych blokadach.

## Draft, akceptacja i późniejsze wykonanie

Po audycie zapisz `docs/plans/<feature>-implementation-plan.md` albo wskazaną ścieżkę. W trybie tylko do odczytu zwróć pełny draft i ścieżkę bez prób zapisu. Status: **DRAFT — do przeglądu użytkownika**. Podaj wynik audytu, otwarte decyzje, pierwszy ograniczony krok i prośbę o dokładny review. Pozostałe blokady oznacz jawnie. **Czekaj na akceptację przed realizacją**; sama prośba o plan jej nie udziela.

Przed przekazaniem sprawdź kompletność informacji i linków, przydziały oraz realność dowodów. Podczas wykonania brief powstaje tuż przed delegacją w trwałej ścieżce projektu, np. `.agent-briefs/<task>.md`. Zawiera wynik, wycinki kontraktów, wyniki poprzedników, dozwolone pliki, równoległe zadania, kroki, dane i oczekiwane wyniki, komendy, zakazy oraz miejsce raportu. Sam link do całego PRD nie wystarcza.

Zaplanuj TDD dla zmian zachowania zgodnie z projektem; dla refaktoryzacji bez zmiany zachowania testy charakteryzujące oryginał. Mocki i fixtures oprzyj na wymaganych przez projekt rzeczywistych capture bez sekretów; brak capture to zależność do rozwiązania, nie wymyślona odpowiedź.

Dowody wiąż z końcowym stanem zmian: wymaganie → sprawdzenie → artefakt → status (`spełnione`, `niespełnione`, `niezweryfikowane`, `nie dotyczy` z powodem). Osobno raportuj build, testy z licznościami i pominięciami, startup oraz ręczne UI/CLI/API. Dokumentacja wymaga kontroli treści, linków i diffu, bez zbędnego startupu. Po ostatniej poprawce ponów właściwy zestaw kontroli; nie sumuj starego przebiegu z pojedynczym retestem jako nowego pełnego wyniku. Wymagaj niezależnego review. Implementacja, ograniczenia jakości danych, publikacja i merge mają osobne statusy i warunki autoryzacji.
