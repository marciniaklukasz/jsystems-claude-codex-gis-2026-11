from __future__ import annotations

import argparse
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from map_qa import config, dashboard_data as dd, store
from map_qa.compare import ATTRIBUTE_LABEL, REASON_TEXT

st.set_page_config(page_title="Kontrola mapy", layout="wide")
st.title("Kontrola mapy — przegląd kandydatów")
# Streamlit forwards script arguments after --; parse_known_args tolerates its own flags.
parser = argparse.ArgumentParser()
parser.add_argument("--runs-dir")
parser.add_argument("--db")
args, _ = parser.parse_known_args(sys.argv[1:])
runs_dir = st.session_state.get("runs_dir") or args.runs_dir or config.DEFAULT_OUT_DIR
db_path = st.session_state.get("db_path") or args.db or config.DEFAULT_DB
st.sidebar.text_input("Autor", key="author")
if st.session_state.get("_flash"):
    st.success(st.session_state.pop("_flash"))
run_dir = dd.latest_run(runs_dir)
if run_dir is None:
    st.info("Brak wyników kontroli — uruchom kontrolę z wiersza poleceń")
    st.stop()
@st.cache_data(show_spinner=False)
def _load(path: str, mtime: float):
    return dd.load_run(Path(path))


with st.spinner("Wczytywanie wyników…"):
    data = _load(str(run_dir), (Path(run_dir) / "candidates.parquet").stat().st_mtime)
st.caption(f'Run {data.run.get("run_id", run_dir.name)} · etap {data.run.get("stage", "") } · {data.run.get("created_at", "")}')
conn = store.connect(db_path)
decisions = store.get_decisions(conn)
overview, fixes = st.tabs(["Przegląd", "Do poprawy"])
with overview:
    attrs = sorted(data.candidates.attribute.unique())
    cats = ["zgodne", "rozbieżne", "do sprawdzenia"]
    reasons = sorted({x for xs in data.candidates.reasons for x in (xs or [])})
    c1, c2, c3, c4 = st.columns(4)
    with c1: f_attr = st.multiselect("Atrybut", attrs, format_func=lambda x: ATTRIBUTE_LABEL.get(x, x), key="f_attr", placeholder="Wybierz…")
    with c2: f_cat = st.multiselect("Kategoria", cats, key="f_cat", placeholder="Wybierz…")
    with c3: f_stage = st.multiselect("Etap", ["1", "2"], key="f_stage", placeholder="Wybierz…")
    with c4: f_reason = st.multiselect("Przyczyna", reasons, format_func=lambda x: REASON_TEXT.get(x, x), key="f_reason", placeholder="Wybierz…")
    filtered = dd.filter_candidates(data.candidates, f_attr, f_cat, f_stage, f_reason)
    order = {"rozbieżne": 0, "do sprawdzenia": 1, "zgodne": 2}  # jak w raporcie (ADR-003 §3.1)
    filtered = filtered.sort_values(["category", "attribute", "osm_id"], key=lambda c: c.map(order) if c.name == "category" else c, kind="stable").reset_index(drop=True)
    st.markdown(f"Liczba pozycji: {len(filtered)}")
    # tabela: najwyżej N pierwszych pozycji (kolejka najpierw); render 51 tys. wierszy trwał ~10 s (ADR-003 D-302)
    max_rows = int(st.session_state.get("_max_table_rows", 2000))
    if len(filtered) > max_rows:
        st.caption(f"Tabela pokazuje {max_rows} pierwszych z {len(filtered)} pozycji — zawęź filtry, aby zobaczyć pozostałe.")
        filtered = filtered.head(max_rows)
    table = dd.review_table(filtered, decisions)
    event = st.dataframe(table, on_select="rerun", selection_mode="single-row", key="table", hide_index=True)
    ids = filtered.candidate_id.tolist()
    # zaznaczenie wiersza w tabeli ustawia wybór kandydata (selectbox = dostęp z klawiatury i testy)
    rows = event.selection.rows if event and event.selection else []
    if rows and rows[0] < len(ids) and st.session_state.get("_table_pick") != ids[rows[0]]:
        st.session_state["_table_pick"] = ids[rows[0]]
        st.session_state["selected"] = ids[rows[0]]
    id_set = set(ids)
    if st.session_state.get("selected") not in id_set:
        st.session_state["selected"] = ids[0] if ids else None
    # lista wyboru: pierwsze 500 pozycji po filtrze + zaznaczona w tabeli (51 tys. opcji blokowało UI, ADR-003 D-302)
    MAX_OPTIONS = 500
    options = ids[:MAX_OPTIONS]
    if st.session_state.get("selected") and st.session_state["selected"] not in options:
        options = options + [st.session_state["selected"]]
    sub = filtered[filtered.candidate_id.isin(options)]
    labels = dict(zip(sub.candidate_id, sub.osm_id.astype(str) + " · " + sub.attribute.map(lambda a: ATTRIBUTE_LABEL.get(a, a)) + " · " + sub.category))
    chosen = st.selectbox("Wybierz kandydata", options=options, key="selected", format_func=lambda cid: f"{cid} · {labels.get(cid, '')}")
    if len(ids) > MAX_OPTIONS:
        st.caption(f"Lista wyboru pokazuje {MAX_OPTIONS} pierwszych z {len(ids)} pozycji — zaznacz wiersz w tabeli albo zawęź filtry.")
    if chosen:
        row = filtered[filtered.candidate_id == chosen].iloc[0]
        detail = dd.candidate_detail(row, data)
        left, right = st.columns(2)
        with left:
            st.subheader("OSM")
            st.write(f'{detail["osm"]["value"]} · {detail["osm"]["date"]}')
            st.code(detail["osm"]["raw"])
        with right:
            st.subheader("Overture")
            st.write(f'{detail["overture"]["value"]} · {detail["overture"]["release"]}')
            st.code(detail["overture"]["raw"])
        st.write(", ".join(detail["reasons"]) or "Brak")
        st.write(detail["reason_text"])
        st.markdown(f'[Otwórz w OpenStreetMap]({detail["osm_url"]})')
        for photo in detail["photos"]:
            if photo["image_bytes"] is not None:
                st.image(photo["image_bytes"], caption=photo["caption"], width=480)
            else:
                st.write(f'{photo["unavailable_text"]} · {photo["caption"]}')
            st.write(photo["link_text"])
            st.write(photo["reading"])
        current = decisions.get(row.candidate_key)
        if current:
            st.markdown(f'Decyzja: {store.DECISION_LABEL[current["decision"]]} · autor {current["author"]} · {current["decided_at"]}')
        options = ["potwierdzony błąd mapy", "brak błędu", "niepewne"]
        # formularz należy do wybranego kandydata: przy zmianie wyboru wczytaj jego zapisaną decyzję albo wyczyść pola
        if st.session_state.get("_form_for") != chosen:
            st.session_state["_form_for"] = chosen
            st.session_state["decision"] = store.DECISION_LABEL[current["decision"]] if current else None
            st.session_state["proposed"] = (current or {}).get("proposed_value") or ""
            st.session_state["comment"] = (current or {}).get("comment") or ""
        choice = st.radio("Decyzja", options, key="decision")
        proposed = st.text_input("Wartość proponowana", key="proposed")
        comment = st.text_area("Komentarz", key="comment")
        if st.button("Zapisz", key="save"):
            if not st.session_state.author.strip():
                st.error("Podaj autora decyzji.")
            elif choice is None:
                st.error("Wybierz decyzję.")
            else:
                code = dict(zip(options, store.DECISIONS))[choice]
                try:
                    store.save_decision(conn, row.candidate_key, code, proposed, comment, st.session_state.author, data.run["run_id"])
                except store.DecisionValidationError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Nie udało się zapisać decyzji: {e}")
                else:
                    st.session_state["_flash"] = "Zapisano decyzję."
                    st.rerun()
with fixes:
    fixes_df = dd.to_fix(data, store.list_confirmed(conn))
    if fixes_df.empty:
        st.info("Brak potwierdzonych przypadków")
    else:
        st.dataframe(fixes_df, hide_index=True, column_config={"OSM": st.column_config.LinkColumn("OSM")})
        # miniatury zdjęć potwierdzonych przypadków (tylko pliki lokalne, AC-25, AC-30)
        for item in dd.to_fix_photos(data, store.list_confirmed(conn)):
            if item["image_bytes"] is not None:
                st.image(item["image_bytes"], caption=f'{item["label"]} — {item["caption"]}', width=320)
            else:
                st.caption(f'{item["label"]} — Zdjęcie niedostępne · {item["caption"]}')
