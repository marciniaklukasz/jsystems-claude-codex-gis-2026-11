# Wytyczne wizualne dashboardu map-qa

**Data:** 2026-11-12 · **Decyzja:** G-DESIGN rozstrzygnięta przez użytkownika w planie orkiestracji ([plan §4, §11](plans/map-qa-full-app-implementation-plan.md)) — **domyślny motyw Streamlit**, bez własnego systemu tokenów. `assets/design-tokens.json` nie jest używany przez dashboard.

## Zasady

- Motyw: domyślny jasny motyw Streamlit 1.66.1 (bez nadpisań w `app/.streamlit/config.toml` poza telemetrią i adresem serwera).
- Język: wszystkie teksty interfejsu po polsku (PRD §8, §11); identyfikatory OSM/Overture, surowe tagi i nazwy pytań bez tłumaczenia.
- Układ: `st.set_page_config(layout="wide")`, tytuł strony „Kontrola mapy — przegląd kandydatów”; pasek boczny z polem „Autor”; dwie zakładki `st.tabs`: „Przegląd” i „Do poprawy” (ADR-003 §3.3).
- Kategorie wyświetlane dokładnie jako `zgodne`, `rozbieżne`, `do sprawdzenia`; decyzje jako „potwierdzony błąd mapy”, „brak błędu”, „niepewne”. Etykieta „potwierdzony błąd mapy” pojawia się przy pozycji wyłącznie po decyzji analityka (AC-14).
- Zdjęcia: tylko z plików lokalnych, szerokość do 480 px, zawsze z podpisem „autor · licencja · źródło” (AC-25); brak pliku → „Zdjęcie niedostępne” z atrybucją.
- Komunikaty stanów (PRD §9.3–9.4): „Brak wyników kontroli — uruchom kontrolę z wiersza poleceń”, „Brak potwierdzonych przypadków”, błąd zapisu przez `st.error` z zachowaniem treści formularza.

## Weryfikacja wizualna

Manual QA (AGENTS.md pkt 5) porównuje zrzuty z tymi zasadami: polskie teksty, czytelne tabele, brak błędów w konsoli. Zgodność z zewnętrzną referencją graficzną nie jest wymagana (brak referencji — decyzja użytkownika).
