"""Dashboard BI — Relación entre caudales (SNIRH/ANA) y clima (NASA POWER).

Ejecutar:  streamlit run app.py
Antes de la primera ejecución hay que correr el ETL (ver README).
"""
from __future__ import annotations

from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

from lib import analisis, carga, geo

st.set_page_config(page_title="Caudales vs. Clima — Piura",
                   page_icon="💧", layout="wide")

RAIZ = Path(__file__).resolve().parent
SELLO = RAIZ / "data" / "ultima_actualizacion.txt"

COLOR_ESTADO = {"Funcionando": "green", "Paralizada": "orange",
                "Cerrada": "gray", "Desconocido": "lightgray"}
COLOR_VAR = {"t2m": "#E4572E", "prectotcorr": "#00A878", "ws2m": "#8338EC"}

# Nombre sencillo de cada variable (para frases en lenguaje simple).
NOMBRE_SIMPLE = {"t2m": "la temperatura", "prectotcorr": "la lluvia",
                 "ws2m": "el viento"}

# Métodos de correlación con etiqueta amable.
METODOS = {"pearson": "Pearson (relación en línea recta)",
           "spearman": "Spearman (aguanta valores extremos)"}

# Sin barra de herramientas en inglés en los gráficos.
PLOTLY_CFG = {"displayModeBar": False, "locale": "es"}


@st.cache_data(show_spinner="Cargando datos…")
def cargar():
    return carga.cargar_todo()


@st.cache_data(show_spinner=False)
def zona_piura():
    """Polígono del departamento de Piura (para pintar la zona en el mapa)."""
    try:
        return geo.region_feature()
    except Exception:
        return None


def ultima_actualizacion() -> str | None:
    return SELLO.read_text(encoding="utf-8").strip() if SELLO.exists() else None


def nivel_fuerza(r: float) -> str:
    """Describe qué tan fuerte es la relación, en palabras simples."""
    a = abs(r)
    if a < 0.2:
        return "casi nada"
    if a < 0.4:
        return "un poco"
    if a < 0.6:
        return "de forma moderada"
    if a < 0.8:
        return "bastante"
    return "muchísimo"


def etiqueta_corta(r: float) -> str:
    if pd.isna(r):
        return "sin datos suficientes"
    juntos = "van juntos" if r >= 0 else "van al revés"
    return f"{juntos} · {nivel_fuerza(r)}"


def frase_relacion(r: float, nombre: str) -> str:
    """Explica la relación en una frase que entienda cualquiera."""
    if pd.isna(r):
        return f"No hay datos suficientes para comparar con {nombre}."
    if r >= 0:
        return (f"Cuando aumenta {nombre}, el caudal del río **también sube** "
                f"({nivel_fuerza(r)}).")
    return (f"Cuando aumenta {nombre}, el caudal del río **baja** "
            f"({nivel_fuerza(r)}).")


def _limites(geom: dict) -> tuple[float, float, float, float]:
    """Recuadro (lon_min, lat_min, lon_max, lat_max) de una geometría GeoJSON."""
    polis = ([geom["coordinates"]] if geom["type"] == "Polygon"
             else geom["coordinates"])
    xs, ys = [], []
    for poli in polis:
        for x, y in poli[0]:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def construir_mapa(est: pd.DataFrame, cob: pd.DataFrame, zona: dict | None = None):
    m = folium.Map(location=[-5.2, -80.3], zoom_start=8, tiles="OpenStreetMap")
    # Pintar la zona de Piura (relleno translúcido, borde marcado).
    if zona is not None:
        folium.GeoJson(
            zona, name="Piura",
            style_function=lambda _: {"fillColor": "#1B98E0", "color": "#0B5C8A",
                                      "weight": 2.5, "fillOpacity": 0.10},
            tooltip="Departamento de Piura",
        ).add_to(m)
        try:
            (x0, y0, x1, y1) = _limites(zona["geometry"])
            m.fit_bounds([[y0, x0], [y1, x1]])
        except Exception:
            pass
    con_datos = set(cob["codigo"]) if not cob.empty else set()
    cluster = MarkerCluster(name="Estaciones").add_to(m)
    for _, r in est.iterrows():
        if pd.isna(r["lat"]) or pd.isna(r["lon"]):
            continue
        tiene = r["codigo"] in con_datos
        popup = folium.Popup(
            f"<b>{r['nombre']}</b><br>Código: {r['codigo']}<br>"
            f"Estado: {r['estado']}<br>"
            f"Caudal: {'sí' if tiene else 'sin datos'}", max_width=250)
        folium.CircleMarker(
            location=[r["lat"], r["lon"]], radius=6 if tiene else 4,
            color=COLOR_ESTADO.get(r["estado"], "lightgray"),
            fill=True, fill_opacity=0.9 if tiene else 0.4, weight=2,
            popup=popup, tooltip=f"{r['nombre']} ({r['codigo']})",
        ).add_to(cluster)
    return m


def grafico_series(men: pd.DataFrame, var: str, etiqueta: str):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=men["fecha"], y=men["caudal"], name="Caudal (m³/s)",
                             mode="lines+markers", marker=dict(size=4),
                             line=dict(color="#1B98E0", width=2),
                             connectgaps=False, yaxis="y1"))
    if var in men.columns:
        fig.add_trace(go.Scatter(x=men["fecha"], y=men[var], name=etiqueta,
                                 mode="lines+markers", marker=dict(size=4),
                                 line=dict(color=COLOR_VAR.get(var, "#888"), width=2),
                                 connectgaps=False, yaxis="y2"))
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(tickformat="%m/%Y", hoverformat="%d/%m/%Y"),
        yaxis=dict(title="Caudal (m³/s)", color="#1B98E0"),
        yaxis2=dict(title=etiqueta, overlaying="y", side="right",
                    color=COLOR_VAR.get(var, "#888")),
        legend=dict(orientation="h", y=1.12), hovermode="x unified",
    )
    return fig


def grafico_dispersion(df: pd.DataFrame, var: str, etiqueta: str):
    d = df[["caudal", var]].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d[var], y=d["caudal"], mode="markers",
                             marker=dict(color=COLOR_VAR.get(var, "#888"),
                                         opacity=0.5, size=6), name="Datos"))
    if len(d) >= 3:
        b, a = np.polyfit(d[var], d["caudal"], 1)
        xs = np.linspace(d[var].min(), d[var].max(), 50)
        fig.add_trace(go.Scatter(x=xs, y=a + b * xs, mode="lines",
                                 line=dict(color="#333", dash="dash"),
                                 name="Tendencia"))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_title=etiqueta, yaxis_title="Caudal (m³/s)",
                      showlegend=False)
    return fig


def bienvenida() -> None:
    st.info(
        "**¿Cómo se usa?**  \n"
        "1️⃣ Elige una estación en el **mapa** (haz clic en un punto) o en la "
        "lista de la derecha.  \n"
        "2️⃣ Mira abajo si el **caudal del río** se parece a **la lluvia, la "
        "temperatura o el viento**.  \n"
        "3️⃣ Cambia las opciones de la **izquierda** para explorar más.")
    with st.expander("📖 ¿Qué significan las palabras? (glosario simple)"):
        st.markdown(
            "- **Caudal:** cuánta agua pasa por el río, en metros cúbicos por "
            "segundo (m³/s). Más caudal = río más lleno.  \n"
            "- **Estación:** un punto donde se mide el río.  \n"
            "- **Relación (correlación):** un número de −1 a +1 que dice qué "
            "tanto se parecen dos cosas. Cerca de **+1**: suben juntas. Cerca "
            "de **0**: no tienen que ver. Cerca de **−1**: cuando una sube, la "
            "otra baja.  \n"
            "- **Desfase:** a veces la lluvia tarda en llegar al río; el "
            "desfase mide ese retraso en meses.  \n"
            "- **NASA POWER:** de ahí sacamos el clima (temperatura, lluvia, "
            "viento) de cada estación desde 1981.")


def main() -> None:
    # Ocultar cromo en inglés de Streamlit + mejorar el aspecto de la interfaz.
    st.markdown("""
        <style>
        :root { --azul:#1B98E0; --azul-osc:#0B5C8A; --tinta:#12354B;
                --borde:#D8E3EC; --panel:#EEF5FA; }

        #MainMenu, footer, [data-testid="stToolbar"],
        [data-testid="stAppDeployButton"],
        [data-testid="InputInstructions"] { display: none !important; }

        /* Barra lateral: panel suave y encabezados claros */
        section[data-testid="stSidebar"] {
            background: var(--panel); border-right: 1px solid var(--borde); }
        section[data-testid="stSidebar"] h2 {
            font-size: .78rem; text-transform: uppercase; letter-spacing: .08em;
            color: #5B7488; font-weight: 700; margin: .6rem 0 .1rem; }

        /* Botones: azul, redondeados, ancho completo, con estado al pasar */
        button[data-testid="stBaseButton-secondary"],
        button[data-testid="stBaseButton-primary"] {
            background: var(--azul) !important; color: #fff !important;
            border: 0 !important; border-radius: 10px !important;
            padding: .55rem 1rem !important; font-weight: 600 !important;
            box-shadow: 0 1px 2px rgba(18,53,75,.15) !important;
            transition: background .15s !important; }
        button[data-testid="stBaseButton-secondary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {
            background: var(--azul-osc) !important; color: #fff !important; }
        button[data-testid="stBaseButton-secondary"]:active { transform: translateY(1px); }

        /* Campos: selectbox, buscador — bordes suaves y foco azul */
        [data-baseweb="select"] > div,
        .stTextInput input, [data-baseweb="input"] {
            border-radius: 10px !important; border-color: var(--borde) !important;
            background: #fff !important; }
        [data-baseweb="select"] > div:focus-within,
        .stTextInput input:focus {
            border-color: var(--azul) !important;
            box-shadow: 0 0 0 2px rgba(27,152,224,.20) !important; }
        [data-baseweb="tag"] { background: var(--azul) !important;
            border-radius: 8px !important; }
        [data-baseweb="tag"] span { color: #fff !important; }

        /* Tarjetas de indicadores (KPIs) */
        [data-testid="stMetric"] {
            background: #fff; border: 1px solid var(--borde); border-radius: 12px;
            padding: .8rem 1rem; box-shadow: 0 1px 3px rgba(18,53,75,.06); }
        [data-testid="stMetricValue"] { color: var(--tinta); font-weight: 700; }

        h1 { color: var(--tinta); }
        </style>
    """, unsafe_allow_html=True)

    datos = cargar()
    est, caudales, clima, cob = (datos["estaciones"], datos["caudales"],
                                 datos["clima"], datos["cobertura"])

    st.title("💧 Caudales vs. Clima — Región Piura")
    st.caption("¿El río crece cuando llueve? ¿Cambia con la temperatura o el "
               "viento? Aquí lo puedes ver estación por estación, en el "
               "departamento de Piura. "
               "Datos: caudales del SNIRH (ANA) y clima de NASA POWER.")

    if est.empty:
        st.warning("No hay datos publicados todavía. Falta subir los archivos "
                   "de datos de Piura al repositorio.")
        return

    bienvenida()

    con_caudal = set(cob["codigo"]) if not cob.empty else set()
    con_clima = set(clima["codigo"]) if not clima.empty else set()

    # --- Barra lateral: filtros y opciones ---------------------------------
    with st.sidebar:
        st.header("Datos")
        sello = ultima_actualizacion()
        st.caption(f"📅 Datos actualizados: **{sello}**" if sello
                   else "📅 Aún no se registra la fecha de actualización.")

        st.header("Filtros")
        zona_sel = "Todas"
        if "ala" in est.columns and est["ala"].notna().any():
            zonas = ["Todas"] + sorted(est["ala"].dropna().unique())
            zona_sel = st.selectbox(
                "Zona de Piura", zonas,
                help="Divide Piura en zonas de agua (ALA): por ejemplo Chira, "
                     "Alto Piura o San Lorenzo. Elige una para ver solo esa parte.")
        estados = st.multiselect(
            "Estado de la estación", sorted(est["estado"].unique()),
            default=sorted(est["estado"].unique()),
            placeholder="Elige uno o más",
            help="Funcionando = mide hoy. Paralizada = pausada. "
                 "Cerrada = ya no mide.")
        solo_clima = st.checkbox(
            "Solo las que se pueden comparar", value=True,
            help="Deja solo estaciones con datos de clima (desde 1981) para "
                 "poder compararlos con el caudal.")
        busca = st.text_input(
            "Buscar estación", placeholder="Nombre o código…",
            help="Escribe parte del nombre o el código.").strip().lower()

        with st.expander("⚙️ Opciones avanzadas"):
            metodo = st.radio(
                "Forma de medir la relación", list(METODOS),
                format_func=lambda m: METODOS[m],
                help="Pearson busca una línea recta; Spearman aguanta mejor los "
                     "valores muy altos o bajos. Si dudas, deja Pearson.")
            escala = st.radio(
                "Juntar los datos por", ["Mensual", "Diaria"], horizontal=True,
                help="Mensual: un promedio por mes (más claro, recomendado). "
                     "Diaria: día por día (más detalle, pero más ruido).")
            max_lag = st.slider(
                "Retraso a revisar (meses)", 0, 12, 6,
                help="La lluvia tarda en llegar al río. Prueba retrasos de 0 a N "
                     "meses y te dice cuál relación sale más fuerte.")

    filtro = est[est["estado"].isin(estados)].copy()
    if zona_sel != "Todas":
        filtro = filtro[filtro["ala"] == zona_sel]
    if solo_clima:
        filtro = filtro[filtro["codigo"].isin(con_clima)]
    if busca:
        filtro = filtro[filtro["nombre"].str.lower().str.contains(busca)
                        | filtro["codigo"].str.contains(busca)]

    # --- KPIs ---------------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estaciones en Piura", f"{len(est):,}",
              help="Puntos donde se mide un río dentro del departamento de Piura.")
    c2.metric("Con datos de caudal", f"{len(con_caudal):,}",
              help="Cuántas tienen medidas del caudal (agua del río).")
    c3.metric("Se pueden comparar", f"{len(con_clima):,}",
              help="Cuántas tienen también datos de clima (desde 1981).")
    c4.metric("En tu filtro", f"{len(filtro):,}",
              help="Cuántas cumplen lo que elegiste a la izquierda.")

    if filtro.empty:
        st.info("Ninguna estación cumple los filtros. Prueba quitar alguno.")
        return

    # --- Selección de estación (sincronizada con el mapa) ------------------
    codigos = filtro["codigo"].tolist()
    if st.session_state.get("sel") not in codigos:
        # Por defecto, la estación con MÁS datos (mejor primera vista).
        pref = [c for c in codigos if c in con_clima] or codigos
        if not cob.empty:
            dias = cob.set_index("codigo")["n_dias"].to_dict()
            pref = sorted(pref, key=lambda c: dias.get(c, 0), reverse=True)
        st.session_state["sel"] = pref[0]

    izq, der = st.columns([1.15, 1])
    with izq:
        st.subheader("🗺️ Mapa de estaciones")
        st.caption("Haz clic en un punto para elegir esa estación. "
                   "🟢 funcionando · 🟠 paralizada · ⚪ cerrada. "
                   "Los puntos grandes tienen datos para comparar.")
        mapa = construir_mapa(filtro, cob, zona_piura())
        estado_mapa = st_folium(mapa, height=460, use_container_width=True,
                                returned_objects=["last_object_clicked"])
        clic = estado_mapa.get("last_object_clicked") if estado_mapa else None
        if clic:
            d = filtro.assign(
                dist=(filtro["lat"] - clic["lat"]).abs()
                + (filtro["lon"] - clic["lng"]).abs())
            cod = d.sort_values("dist").iloc[0]
            if cod["dist"] < 0.02 and cod["codigo"] != st.session_state["sel"]:
                st.session_state["sel"] = cod["codigo"]
                st.rerun()

    with der:
        st.subheader("📍 Estación elegida")
        idx = codigos.index(st.session_state["sel"])
        etq_opts = {c: f"{r['nombre']} ({c})"
                    for c, r in filtro.set_index("codigo").iterrows()}
        sel = st.selectbox("Elige una estación", codigos, index=idx,
                           format_func=lambda c: etq_opts[c],
                           placeholder="Elige una estación",
                           help="También puedes hacer clic en el mapa.")
        if sel != st.session_state["sel"]:
            st.session_state["sel"] = sel
            st.rerun()

        info = filtro[filtro["codigo"] == sel].iloc[0]
        rio = ""
        if not cob.empty and sel in set(cob["codigo"]):
            valor_rio = cob[cob["codigo"] == sel].iloc[0].get("rio")
            rio = "" if pd.isna(valor_rio) else str(valor_rio)
        zona_est = (str(info["ala"]) if "ala" in info
                    and pd.notna(info["ala"]) else "")
        zona_txt = f"Zona: {zona_est}" if zona_est else ""
        detalle = "  \n".join(x for x in [zona_txt, rio] if x)
        st.markdown(f"**{info['nombre']}**  \nCódigo {sel} · {info['tipo']} · "
                    f"{info['estado']}" + (f"  \n{detalle}" if detalle else ""))
        if not cob.empty and sel in set(cob["codigo"]):
            cc = cob[cob["codigo"] == sel].iloc[0]
            st.caption(f"Tiene datos de caudal desde "
                       f"{pd.Timestamp(cc['fecha_min']):%d/%m/%Y} hasta "
                       f"{pd.Timestamp(cc['fecha_max']):%d/%m/%Y} "
                       f"({cc['n_dias']:,} días).")

    # --- Datos de la estación seleccionada ---------------------------------
    diario = carga.serie_estacion(caudales, clima, sel)
    if diario.empty:
        st.info("Esta estación no tiene datos de caudal descargados. "
                "Elige otra en el mapa o en la lista.")
        return
    df = diario if escala == "Diaria" else carga.agregar_mensual(diario)

    st.divider()
    st.subheader(f"¿Se parece el caudal al clima? — {info['nombre']}")

    tabla = analisis.correlaciones(df, metodo)
    if tabla.empty or tabla["r"].isna().all():
        st.warning("Esta estación no tiene suficientes datos de clima para "
                   "comparar. Prueba con otra (las de puntos grandes en el mapa "
                   "sí tienen).")
        return

    # Conclusión en palabras: la variable que más se relaciona.
    val = tabla.dropna(subset=["r"])
    if not val.empty:
        top = val.loc[val["r"].abs().idxmax()]
        nombre_top = NOMBRE_SIMPLE.get(top["variable"], top["etiqueta"])
        st.success(f"🔎 **En pocas palabras:** aquí el caudal se relaciona sobre "
                   f"todo con **{nombre_top}**. {frase_relacion(top['r'], nombre_top)}")

    st.caption("El número **r** va de −1 a +1: cerca de +1 suben juntos, cerca "
               "de 0 no tienen que ver, cerca de −1 uno sube y el otro baja.")
    cols = st.columns(len(carga.VARIABLES))
    for col, (_, fila) in zip(cols, tabla.iterrows()):
        col.metric(fila["etiqueta"],
                   "—" if pd.isna(fila["r"]) else f"r = {fila['r']:.2f}",
                   help="'van juntos' = suben a la vez. 'van al revés' = cuando "
                        "uno sube el otro baja.")
        flecha = "" if pd.isna(fila["r"]) else ("🟢 " if fila["r"] >= 0 else "🔴 ")
        col.caption(f"{flecha}{etiqueta_corta(fila['r'])}")

    # Variable a explorar en detalle
    var_sel = st.selectbox(
        "Mira una variable en detalle", list(carga.VARIABLES.keys()),
        format_func=lambda v: f"{carga.VARIABLES[v][0]} ({carga.VARIABLES[v][1]})",
        placeholder="Elige una variable",
        help="Elige qué variable del clima quieres comparar con el caudal.")
    etiqueta = f"{carga.VARIABLES[var_sel][0]} ({carga.VARIABLES[var_sel][1]})"
    nombre_var = NOMBRE_SIMPLE.get(var_sel, etiqueta)

    g1, g2 = st.columns([1.4, 1])
    with g1:
        st.markdown(f"**El caudal y {nombre_var} a lo largo del tiempo**")
        st.caption("Línea azul: caudal del río. Línea de color: la variable del "
                   "clima. Si suben y bajan a la vez, están relacionados.")
        st.plotly_chart(grafico_series(df, var_sel, etiqueta),
                        width="stretch", config=PLOTLY_CFG)
    with g2:
        st.markdown(f"**Cada punto compara {nombre_var} con el caudal**")
        st.caption("Si los puntos siguen la línea que sube, más "
                   f"{nombre_var.replace('la ', '').replace('el ', '')} = más caudal.")
        st.plotly_chart(grafico_dispersion(df, var_sel, etiqueta),
                        width="stretch", config=PLOTLY_CFG)

    # Desfase temporal (solo tiene sentido en mensual)
    if escala == "Mensual" and var_sel in df.columns:
        ml = analisis.mejor_lag(df["caudal"], df[var_sel], max_lag, metodo)
        if not pd.isna(ml["r"]):
            if ml["lag"] == 0:
                st.info(f"⏱️ La relación con {nombre_var} es más fuerte **el "
                        f"mismo mes** (r = {ml['r']:.2f}).")
            else:
                st.info(f"⏱️ La relación con {nombre_var} es más fuerte "
                        f"**{ml['lag']} mes(es) después** (r = {ml['r']:.2f}). "
                        f"Es decir, {nombre_var} de hace {ml['lag']} mes(es) "
                        "se parece al caudal de ahora.")

    with st.expander("🔬 Ver números y calidad de datos"):
        st.write(f"Datos usados ({escala.lower()}): "
                 f"{int(df['caudal'].notna().sum()):,} · "
                 f"Método: {METODOS[metodo]}")
        st.dataframe(tabla.assign(fuerza=tabla["r"].map(etiqueta_corta)).rename(
            columns={"etiqueta": "Variable del clima", "r": "Relación (r)",
                     "n": "Datos comparados", "fuerza": "En palabras"})
            [["Variable del clima", "Relación (r)", "Datos comparados",
              "En palabras"]], hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
