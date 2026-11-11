"""Interfaz local (Streamlit) para explorar la última ejecución.

Lanzar con:  uv run electoral ui
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from electoral_lab.storage import paths

st.set_page_config(page_title="Electoral Lab · 29-N", layout="wide")


# ---------------------------------------------------------------- carga
def list_runs() -> list[Path]:
    if not paths.RUNS.exists():
        return []
    return sorted((p for p in paths.RUNS.iterdir() if (p / "manifest.json").exists()), reverse=True)


@st.cache_data(show_spinner=False)
def load_run(run_dir: str) -> dict:
    d = Path(run_dir)
    out: dict = {"manifest": json.loads((d / "manifest.json").read_text())}
    for name in ["national_summary", "national_trend", "house_effects", "seats_national", "seats_province",
                 "votes_province", "pivotal", "polls_used"]:
        f = d / f"{name}.csv"
        out[name] = pd.read_csv(f, dtype={"province": str}) if f.exists() else pd.DataFrame()
    f = d / "pivotal_detail.json"
    out["pivotal_detail"] = json.loads(f.read_text()) if f.exists() else {}
    f = d / "sims.npz"
    if f.exists():
        z = np.load(f, allow_pickle=True)  # fichero local generado por el propio pipeline
        out["sims"] = {k: z[k] for k in z.files}
    return out


def load_dist(run_dir: str, code: str, party: str) -> np.ndarray | None:
    f = Path(run_dir) / f"dist_next_{code}_{party}.npy"
    return np.load(f) if f.exists() else None


# ---------------------------------------------------------------- barra lateral
st.sidebar.title("Electoral Lab")
st.sidebar.caption("Generales 29-N-2026 · eficacia marginal del voto")
runs = list_runs()

with st.sidebar.expander("Nueva ejecución", expanded=not runs):
    provs = st.text_input("Circunscripciones para E_p,c", "Málaga Madrid Bilbao")
    nsims = st.number_input("Simulaciones", 2000, 100000, 20000, step=2000)
    sigma = st.slider("Escala σ territorial", 0.4, 1.5, 1.0, 0.1)
    refresh = st.checkbox("Actualizar fuentes antes (requiere red)", value=False)
    if st.button("Ejecutar pipeline"):
        base = [sys.executable, "-m", "electoral_lab.cli.main"]
        log = ""
        with st.spinner("Ejecutando… (≈1 min con 20 000 simulaciones)"):
            if refresh:
                r0 = subprocess.run([*base, "sources", "refresh"], capture_output=True, text=True, cwd=paths.ROOT)
                log += r0.stdout + r0.stderr
            cmd = [*base, "run", *provs.split(), "--sims", str(int(nsims)), "--set", f"territorial.sigma_scale={sigma}"]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=paths.ROOT)
            log += res.stdout + res.stderr
        st.code(log[-4000:])
        st.cache_data.clear()
        runs = list_runs()

if not runs:
    st.info("No hay ejecuciones todavía. Lanza `uv run electoral run Málaga Madrid Bilbao` o usa el panel lateral.")
    st.stop()

run_dir = st.sidebar.selectbox("Ejecución", runs, format_func=lambda p: p.name)
R = load_run(str(run_dir))
M = R["manifest"]
st.sidebar.markdown(
    f"**Último sondeo:** {M.get('last_poll')}  \n**Sondeos usados:** {M.get('n_polls')}  \n"
    f"**Simulaciones:** {M.get('n_sims'):,}  \n**Semilla:** {M.get('seed')}  \n"
    f"**Hash datos/config:** `{M.get('data_hash')}` / `{M.get('config_hash')}`"
)

tab_e, tab_n, tab_c, tab_f, tab_a = st.tabs(
    ["Efecto marginal E_p,c", "Modelo nacional", "Circunscripción", "Fuentes y sondeos", "Auditoría"]
)

# ---------------------------------------------------------------- E_p,c
with tab_e:
    st.header("Eficacia marginal de un voto")
    st.markdown(
        r"$E_{p,c}=\Pr(\text{un voto adicional a } p \text{ en } c \text{ cambia el reparto de escaños})$. "
        "Se muestra por 100 000 votos y como «1 entre N»."
    )
    piv = R["pivotal"]
    if piv.empty:
        st.warning("Esta ejecución no calculó E_p,c.")
    else:
        names = piv.drop_duplicates("province")[["province", "province_name"]].values.tolist()
        code = st.radio("Circunscripción", [c for c, _ in names],
                        format_func=lambda c: dict(names)[c], horizontal=True)
        sub = piv[piv.province == code].sort_values("E", ascending=False)
        show = sub[["party", "seats_mean", "E_per_100k", "one_in", "M1000", "direct_M1000",
                    "median_votes_to_next", "top_displaced"]].rename(columns={
                        "party": "Partido", "seats_mean": "Escaños (media)", "E_per_100k": "E ×100k",
                        "one_in": "1 entre", "M1000": "P(+1000 votos cambian)", "direct_M1000": "Contraste MC",
                        "median_votes_to_next": "Votos al siguiente (mediana)", "top_displaced": "Desplaza a"})
        st.dataframe(show.style.format({"Escaños (media)": "{:.2f}", "E ×100k": "{:.3f}", "1 entre": "{:,.0f}",
                                        "P(+1000 votos cambian)": "{:.4f}", "Contraste MC": "{:.4f}",
                                        "Votos al siguiente (mediana)": "{:,.0f}"}),
                     width="stretch", hide_index=True)
        chart = alt.Chart(sub).mark_bar().encode(
            x=alt.X("E_per_100k:Q", title="E por 100 000 votos"),
            y=alt.Y("party:N", sort="-x", title=None),
            tooltip=["party", alt.Tooltip("E_per_100k:Q", format=".3f"), alt.Tooltip("one_in:Q", format=",.0f")],
        )
        st.altair_chart(chart, width="stretch")

        party = st.selectbox("Detalle de partido", sub.party.tolist())
        det = R["pivotal_detail"].get(f"{code}_{party}", {})
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("A quién quitaría el escaño")
            if det.get("displaced"):
                dd = pd.DataFrame({"partido": list(det["displaced"]), "prob": list(det["displaced"].values())})
                st.altair_chart(alt.Chart(dd).mark_bar().encode(
                    x=alt.X("prob:Q", axis=alt.Axis(format="%")), y=alt.Y("partido:N", sort="-x")),
                    width="stretch")
            if det.get("causes"):
                st.caption("Causa del cambio: " + ", ".join(f"{k} {v:.0%}" for k, v in det["causes"].items()))
        with c2:
            st.subheader("Votos que faltan para el siguiente escaño")
            dist = load_dist(str(run_dir), code, party)
            if dist is not None:
                v = pd.DataFrame({"votos": dist[np.isfinite(dist)]})
                v = v[v.votos < v.votos.quantile(0.98)]
                st.altair_chart(alt.Chart(v).mark_bar().encode(
                    x=alt.X("votos:Q", bin=alt.Bin(maxbins=60), title="votos adicionales"),
                    y=alt.Y("count():Q", title="simulaciones")), width="stretch")
        st.caption("Estimador Rao-Blackwell condicional (densidad del umbral en 0). "
                   "«Contraste MC» = Monte Carlo directo con +1000 votos, como validación.")

# ---------------------------------------------------------------- nacional
with tab_n:
    st.header("Intención de voto nacional (día de la elección)")
    ns = R["national_summary"]
    if not ns.empty:
        t = ns[["group", "E_mean", "E_lo", "E_hi", "n_obs", "house_sd"]].copy()
        for c in ["E_mean", "E_lo", "E_hi"]:
            t[c] = 100 * t[c]
        st.dataframe(t.rename(columns={"group": "Grupo", "E_mean": "% medio", "E_lo": "% p05", "E_hi": "% p95",
                                       "n_obs": "Sondeos", "house_sd": "σ efecto casa"}),
                     width="stretch", hide_index=True)
    tr = R["national_trend"]
    if not tr.empty:
        groups = st.multiselect("Grupos", sorted(tr.group.unique()), default=["PP", "PSOE", "VOX", "FA_FV"])
        tt = tr[tr.group.isin(groups)].copy()
        tt["date"] = pd.to_datetime(tt["date"])
        base = alt.Chart(tt).encode(x="date:T", color="group:N")
        st.altair_chart(base.mark_area(opacity=0.2).encode(y=alt.Y("lo:Q", axis=alt.Axis(format="%"), title="cuota"),
                                                            y2="hi:Q") + base.mark_line().encode(y="share:Q"),
                        width="stretch")
    st.subheader("Escaños nacionales")
    sn = R["seats_national"]
    if not sn.empty:
        st.dataframe(sn.rename(columns={"party": "Partido", "mean": "Media", "p05": "p05", "p50": "Mediana",
                                        "p95": "p95", "p_largest": "P(1º)"}),
                     width="stretch", hide_index=True)
    b = M.get("bloc_summary", {})
    if b:
        st.metric("P(PP+VOX ≥ 176)", f"{b.get('p_right_majority', 0):.0%}")
    sims = R.get("sims")
    if sims is not None:
        ents = [str(e) for e in sims["entities"]]
        p = st.selectbox("Distribución de escaños", ents, index=0)
        h = pd.DataFrame({"escaños": sims["seats_total"][:, ents.index(p)]})
        st.altair_chart(alt.Chart(h).mark_bar().encode(x=alt.X("escaños:O"), y="count():Q"),
                        width="stretch")

# ---------------------------------------------------------------- circunscripción
with tab_c:
    st.header("Resultados simulados por circunscripción")
    sp, vp = R["seats_province"], R["votes_province"]
    if not sp.empty:
        names = sp.drop_duplicates("province").set_index("province")["province_name"].to_dict()
        code = st.selectbox("Provincia", list(names), format_func=lambda c: f"{names[c]} ({c})",
                            index=list(names).index("29") if "29" in names else 0)
        s = sp[sp.province == code].merge(vp[vp.province == code], on=["province", "party"], how="left")
        s = s[(s["mean"] > 0.01) | (s.share_mean > 0.01)].sort_values("mean", ascending=False)
        st.caption(f"{int(s.seats_total.iloc[0])} escaños en juego")
        for c in ["share_mean", "share_p05", "share_p95"]:
            s[c] = 100 * s[c]
        st.dataframe(s[["party", "share_mean", "share_p05", "share_p95", "p_over_3pct", "mean", "p05", "p95",
                        "p_at_least_1"]].rename(columns={
                            "party": "Partido", "share_mean": "% voto", "share_p05": "% p05", "share_p95": "% p95",
                            "p_over_3pct": "P(≥3%)", "mean": "Escaños", "p05": "Esc. p05", "p95": "Esc. p95",
                            "p_at_least_1": "P(≥1 escaño)"}),
                     width="stretch", hide_index=True)

# ---------------------------------------------------------------- fuentes
with tab_f:
    st.header("Sondeos usados y efectos casa")
    pu = R["polls_used"]
    st.dataframe(pu.sort_values("fieldwork_end", ascending=False), width="stretch", hide_index=True)
    he = R["house_effects"]
    if not he.empty:
        g = st.selectbox("Efecto casa del grupo", sorted(he.group.unique()))
        st.altair_chart(alt.Chart(he[he.group == g]).mark_bar().encode(
            x=alt.X("house_logit:Q", title="sesgo (logit)"), y=alt.Y("pollster:N", sort="-x")),
            width="stretch")
    st.subheader("Ficheros de datos")
    st.json(M.get("data_files", {}))

# ---------------------------------------------------------------- auditoría
with tab_a:
    st.header("Auditoría y reproducibilidad")
    st.markdown(f"**Modelo σ territorial:** {M.get('sigma_model', {}).get('notes', '')}")
    st.markdown(f"**Error de calibración nacional:** {M.get('calib_error', float('nan')):.4f}")
    st.json(M, expanded=False)
    st.code(f"uv run electoral report {run_dir.relative_to(paths.ROOT)}")
