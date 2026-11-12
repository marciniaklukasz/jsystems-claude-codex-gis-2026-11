"""Dashboard Streamlit przez AppTest (bez przeglądarki): ADR-003 §3.3, §8; PRD §9.3–9.4, AC-14, AC-27–AC-29; TAC-003-03.

Kontrakt UI (zapisany w docs/design-guidelines.md):
- tytuł „Kontrola mapy — przegląd kandydatów”; pasek boczny: text_input „Autor” (key="author");
- zakładki „Przegląd”, „Do poprawy”;
- filtry multiselect „Atrybut” (f_attr), „Kategoria” (f_cat), „Etap” (f_stage), „Przyczyna” (f_reason); licznik „Liczba pozycji: N”;
- tabela st.dataframe z zaznaczeniem wiersza + selectbox „Wybierz kandydata” (key="selected", wartości = candidate_id);
- formularz: radio „Decyzja” (key="decision"), text_input „Wartość proponowana” (key="proposed"), text_area „Komentarz” (key="comment"), przycisk „Zapisz”.
Ścieżki: session_state["runs_dir"], session_state["db_path"] (w produkcji argumenty `-- --runs-dir --db`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_dashboard_logic import make_run  # noqa: E402

APP = Path(__file__).resolve().parents[2] / "dashboard" / "app.py"


def new_app(runs_dir: Path, db: Path) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.session_state["runs_dir"] = str(runs_dir)
    at.session_state["db_path"] = str(db)
    return at.run()


def texts(at) -> str:
    parts = [m.value for m in at.markdown] + [m.value for m in at.caption] + [m.value for m in at.info] + \
            [m.value for m in at.success] + [m.value for m in at.error] + [m.value for m in at.warning]
    return "\n".join(str(p) for p in parts)


@pytest.fixture()
def env(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs)
    return runs, tmp_path / "data" / "map_qa.db"


def test_empty_state_without_runs(tmp_path):
    at = new_app(tmp_path / "none", tmp_path / "t.db")
    assert not at.exception
    assert "Brak wyników kontroli — uruchom kontrolę z wiersza poleceń" in texts(at)


def test_layout_title_tabs_filters(env):
    at = new_app(*env)
    assert not at.exception
    assert at.title[0].value == "Kontrola mapy — przegląd kandydatów"
    assert [t.label for t in at.tabs] == ["Przegląd", "Do poprawy"]
    labels = [m.label for m in at.multiselect]
    assert labels == ["Atrybut", "Kategoria", "Etap", "Przyczyna"]
    assert at.text_input(key="author").label == "Autor"
    assert "Liczba pozycji: 5" in texts(at)


def test_filter_category_count(env):  # AC-27
    at = new_app(*env)
    at.multiselect(key="f_cat").select("rozbieżne").run()
    assert "Liczba pozycji: 2" in texts(at)
    assert set(at.selectbox(key="selected").options) <= {"c1", "c5"} or len(at.selectbox(key="selected").options) == 2


def test_filter_stage_uses_attribute_stage(env):  # P4
    at = new_app(*env)
    at.multiselect(key="f_stage").select("2").run()
    assert "Liczba pozycji: 2" in texts(at)


def test_no_map_error_label_without_decision(env):  # AC-14
    at = new_app(*env)
    for df in at.dataframe:
        assert "błąd mapy" not in df.value.to_string()


def test_confirmed_without_proposed_value_shows_error_and_keeps_text(env):  # ADR-003 §3.2, PRD §9.3
    runs, db = env
    at = new_app(runs, db)
    at.text_input(key="author").set_value("anna")
    at.selectbox(key="selected").set_value("c1").run()
    at.radio(key="decision").set_value("potwierdzony błąd mapy")
    at.text_area(key="comment").set_value("znak 70 widoczny")
    at.button(key="save").click().run()
    assert any("wymaga wartości proponowanej" in e.value for e in at.error)
    assert at.text_area(key="comment").value == "znak 70 widoczny"
    from map_qa import store
    assert store.get_decisions(store.connect(db)) == {}


def test_missing_author_blocks_save(env):
    at = new_app(*env)
    at.selectbox(key="selected").set_value("c1").run()
    at.radio(key="decision").set_value("brak błędu")
    at.button(key="save").click().run()
    assert any("autora" in e.value for e in at.error)


def test_save_decision_persists_after_restart_and_to_fix_tab(env):  # AC-28, AC-29, TAC-003-03
    runs, db = env
    at = new_app(runs, db)
    assert "Brak potwierdzonych przypadków" in texts(at)
    at.text_input(key="author").set_value("anna")
    at.selectbox(key="selected").set_value("c1").run()
    at.radio(key="decision").set_value("potwierdzony błąd mapy")
    at.text_input(key="proposed").set_value("70")
    at.text_area(key="comment").set_value("znak 70")
    at.button(key="save").click().run()
    assert not at.exception
    assert any("Zapisano decyzję" in s.value for s in at.success)

    at2 = new_app(runs, db)  # „restart” — nowa sesja, ten sam plik SQLite
    at2.selectbox(key="selected").set_value("c1").run()
    t = texts(at2)
    assert "potwierdzony błąd mapy" in t and "anna" in t
    fix = [df.value for df in at2.dataframe if "wartość proponowana" in df.value.columns]
    assert len(fix) == 1 and len(fix[0]) == 1
    assert fix[0].iloc[0]["OSM"] == "https://www.openstreetmap.org/way/101" and fix[0].iloc[0]["wartość proponowana"] == "70"
    assert "Brak potwierdzonych przypadków" not in texts(at2)
