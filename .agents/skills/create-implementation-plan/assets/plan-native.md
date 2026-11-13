## Wariant native-only — wbudowane subagenty

Dołącz tę sekcję do wypełnionej części wspólnej. Nie deleguj przez zewnętrzne CLI. Dotyczy to również audytu planu i review implementacji.

| Rola / zadania z macierzy | Natywny mechanizm | Model i uzasadnienie, jeśli wybieralny | Uprawnienia / limit równoległości | Zatwierdzone zastępstwo |
|---|---|---|---|---|
| {orkiestrator} | {główna sesja} | {wybór} | {integracja i przydzielone pliki} | {decyzja} |
| {wykonawca: ID zadań} | {rzeczywiste narzędzie subagentów} | {wybór} | {zakres i ograniczenia} | {decyzja} |
| {audytor / recenzent} | {natywny niezależny subagent} | {wybór} | {tylko odczyt} | {decyzja} |

### Procedura delegowania

1. Potwierdź w bieżącym harnessie tworzenie, oczekiwanie i odbiór wyniku subagenta. Zapisz, co sprawdzono, a co będzie smoke testem po akceptacji. Nie zakładaj uprawnień lub modeli z innego narzędzia.
2. Po akceptacji wykonania wybierz gotowe zadanie z macierzy i przygotuj trwały brief. Przekaż potrzebny kontekst oraz informację o równoległych pracach. Zapisz identyfikator agenta i zadania w trackerze.
3. Ogranicz edycję do przydzielonych plików i wymagaj raportu. Zakaz w briefie opisz oddzielnie od blokady technicznej. Sprawdź zakres diffu i Git, odtwórz kontrole, potem integruj wynik.
4. Przy bezczynności lub niepowodzeniu stosuj limit prób i uzgodnione zastępstwa. Jeśli natywne delegowanie jest niedostępne, zapytaj o zmianę wariantu lub wykonawcy. Nie zastępuj go cicho CLI ani pracą orkiestratora.

**Wiążąca zasada:** zadania przypisane subagentom muszą zostać im zlecone. Przejęcie przez orkiestratora wymaga wcześniej uzgodnionego zastępstwa albo nowej decyzji użytkownika zapisanej w trackerze.
