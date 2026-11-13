## Wariant headless-cli — delegowanie między narzędziami

Dołącz tę sekcję do wypełnionej części wspólnej. Jawnie przypisz zadania CLI i natywnym subagentom. Nie zakładaj konkretnych dostawców, modeli ani subskrypcji.

| Rola / zadania | Narzędzie, wersja, model / dostawca | Uprawnienia i koszt | Brief / raport / log | Zatwierdzone zastępstwo |
|---|---|---|---|---|
| {ID zadań} | {potwierdzony wybór} | {sandbox, zgody, budżet} | {trwałe ścieżki} | {decyzja} |
| {niezależny audytor / recenzent} | {narzędzie} | {tylko odczyt} | {ścieżki} | {decyzja} |

### Krótka instrukcja uruchomienia

{Wstaw komendy po sprawdzeniu pomocy zainstalowanej wersji. Podaj wersję, katalog roboczy i powłokę. Nie kopiuj historycznych flag lub cen.}

| Operacja | Potwierdzona komenda / mechanizm | Co potwierdzono, czego nie sprawdzono |
|---|---|---|
| Wersja i pomoc | {lokalne --help / --version} | {wynik} |
| Uruchomienie | {program, headless, model, cwd, sandbox, wejście briefu i raport} | {źródło składni} |
| Odbiór i zatrzymanie | {kod wyjścia, raport/log, identyfikator procesu, przerwanie} | {limit bezczynności} |

Nie zamieszczaj wykonywalnego przykładu z niepotwierdzonymi opcjami. Jeśli narzędzia nie ma, pokaż brak i zapytaj o alternatywę. Nie instaluj ani nie uwierzytelniaj narzędzi bez odpowiedniej zgody.

### Kontrakt wykonania

1. Przekaż brief przez obsługiwany plik lub stdin. Wymagaj raportu w trwałej ścieżce i zachowaj log. Cytowanie argumentów musi pasować do powłoki, bez podstawiania poleceń z treści briefu.
2. Ustal zachowanie przy pytaniu o zgodę bez terminala, dostęp do cache/środowiska, ograniczenia sieci i Git. Bez sekretów w briefie i logu. Nie rozwiązuj blokady cache przez ogólne wyłączenie sandboxa lub wszystkich zgód.
3. Po akceptacji przewidź ograniczony smoke test na nieszkodliwym zadaniu, jeśli headless, uprawnienia lub cache są nieznane. Test nie tworzy prawdziwych commitów ani nie publikuje. Rozróżnij pomoc, próbę uruchomienia i potwierdzone działanie.
4. Zapisz limit bezczynności i prób, zatrzymanie tylko własnego procesu, odbiór częściowych wyników i zastępstwo. Sam kod 0 nie wystarcza: sprawdź raport, zakres diffu, testy i wynik. Orkiestrator reprodukuje kontrole przed integracją.

**Wiążąca zasada:** użyj wykonawcy z macierzy. Awaria nie upoważnia orkiestratora do przejęcia zadania bez uzgodnionego zastępstwa albo nowej decyzji użytkownika zapisanej w trackerze.
