"""Indicadores de línea base de la información hidroclimática.

Ocho dimensiones calculadas solo con los datos ya descargados por el ETL:
disponibilidad, completitud, continuidad, calidad, actualidad, cobertura
meteorológica, cobertura conjunta y complementación con el reanálisis.

Funciones puras (sin Streamlit): reciben los DataFrames del ETL y devuelven un
resultado por estación o un resumen de red.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# NASA POWER no publica datos antes de 1981; las brechas de caudal previas a esa
# fecha no pueden contextualizarse con el reanálisis climático.
CLIMA_INICIO = pd.Timestamp("1981-01-01")
_VACIA = pd.Series(dtype="float64", index=pd.DatetimeIndex([]))


def _ts(fecha) -> pd.Timestamp:
    """A Timestamp. En `cobertura` las fechas llegan como `datetime.date`."""
    return pd.Timestamp(fecha)


def _series_caudal(caudales: pd.DataFrame) -> dict[str, pd.Series]:
    """Caudal por estación indexado por fecha, en un solo recorrido del DataFrame.

    Evita reescanear las decenas de miles de filas de caudales una vez por cada
    estación y por cada indicador.
    """
    if caudales.empty:
        return {}
    salida: dict[str, pd.Series] = {}
    for cod, g in caudales.groupby("codigo"):
        s = g.set_index("fecha")["caudal"].sort_index()
        salida[cod] = s[~s.index.duplicated(keep="first")]
    return salida


def _fechas_clima(clima: pd.DataFrame) -> dict[str, set]:
    """Fechas (como `date`) con clima observado (t2m no nulo) por estación."""
    if clima.empty or "t2m" not in clima.columns:
        return {}
    val = clima.loc[clima["t2m"].notna()]
    return {cod: set(pd.to_datetime(g["fecha"]).dt.date)
            for cod, g in val.groupby("codigo")}


def _rango_diario(fecha_min, fecha_max) -> pd.DatetimeIndex:
    return pd.date_range(_ts(fecha_min), _ts(fecha_max), freq="D")


def _rangos_clima(clima: pd.DataFrame) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """Primera y última fecha de clima por estación."""
    if clima.empty:
        return {}
    g = clima.groupby("codigo")["fecha"].agg(["min", "max"])
    return {cod: (pd.Timestamp(f["min"]), pd.Timestamp(f["max"]))
            for cod, f in g.iterrows()}


def _mayor_tramo_nan(mask_falta: pd.Series) -> tuple[int, int]:
    """(longitud del mayor tramo consecutivo de faltantes, nº de tramos).

    `mask_falta` es booleana sobre el rango diario completo (True = día sin dato).
    """
    if not bool(mask_falta.any()):
        return (0, 0)
    bloque = (mask_falta != mask_falta.shift()).cumsum()
    por_bloque = mask_falta.groupby(bloque)
    tam = por_bloque.sum()
    es_falta = por_bloque.first()
    faltas = tam[es_falta]
    if faltas.empty:
        return (0, 0)
    return (int(faltas.max()), int(len(faltas)))


# --- Indicadores a nivel de red --------------------------------------------

def disponibilidad(estaciones: pd.DataFrame, cobertura: pd.DataFrame,
                   clima: pd.DataFrame) -> dict:
    """Estaciones con datos frente al total de la red."""
    total = len(estaciones)
    con_caudal = int(cobertura["codigo"].nunique()) if not cobertura.empty else 0
    con_clima = int(clima["codigo"].nunique()) if not clima.empty else 0
    return {
        "total": total,
        "con_caudal": con_caudal,
        "con_clima": con_clima,
        "disp_caudal": con_caudal / total * 100 if total else np.nan,
    }


def cobertura_meteo(cobertura: pd.DataFrame, clima: pd.DataFrame) -> dict:
    """Estaciones con caudal que además tienen clima asociable."""
    if cobertura.empty:
        return {"con_caudal": 0, "con_ambos": 0, "ratio": np.nan}
    n_caudal = int(cobertura["codigo"].nunique())
    cods_clima = set(clima["codigo"].unique()) if not clima.empty else set()
    con_ambos = len(set(cobertura["codigo"].unique()) & cods_clima)
    return {
        "con_caudal": n_caudal,
        "con_ambos": con_ambos,
        "ratio": con_ambos / n_caudal * 100 if n_caudal else np.nan,
    }


# --- Indicadores por estación ----------------------------------------------

def completitud_estacion(caudales: pd.DataFrame, cobertura: pd.DataFrame,
                         series: dict | None = None) -> pd.DataFrame:
    """Días con dato frente a los esperados en el rango de cada estación."""
    series = series if series is not None else _series_caudal(caudales)
    filas = []
    for _, c in cobertura.iterrows():
        serie = series.get(c["codigo"], _VACIA)
        esperados = (_ts(c["fecha_max"]) - _ts(c["fecha_min"])).days + 1
        validos = int(serie.notna().sum())
        comp = min(validos / esperados * 100, 100.0) if esperados else np.nan
        filas.append({"codigo": c["codigo"], "esperados": esperados,
                      "validos": validos, "completitud": comp})
    return pd.DataFrame(filas)


def continuidad_estacion(caudales: pd.DataFrame, cobertura: pd.DataFrame,
                         series: dict | None = None) -> pd.DataFrame:
    """Mayor tramo de días consecutivos sin dato dentro del rango."""
    series = series if series is not None else _series_caudal(caudales)
    filas = []
    for _, c in cobertura.iterrows():
        serie = series.get(c["codigo"], _VACIA)
        diaria = serie.reindex(_rango_diario(c["fecha_min"], c["fecha_max"]))
        hueco_max, n_huecos = _mayor_tramo_nan(diaria.isna())
        filas.append({"codigo": c["codigo"], "hueco_max_dias": hueco_max,
                      "n_huecos": n_huecos})
    return pd.DataFrame(filas)


def calidad_estacion(caudales: pd.DataFrame, cobertura: pd.DataFrame,
                     series: dict | None = None) -> pd.DataFrame:
    """Registros que pasan un control físico básico (caudal no nulo y ≥ 0)."""
    series = series if series is not None else _series_caudal(caudales)
    filas = []
    for _, c in cobertura.iterrows():
        serie = series.get(c["codigo"], _VACIA)
        disponibles = int(serie.notna().sum())
        validos = int(((serie.notna()) & (serie >= 0)).sum())
        cal = validos / disponibles * 100 if disponibles else np.nan
        filas.append({"codigo": c["codigo"], "disponibles": disponibles,
                      "validos_control": validos, "calidad": cal})
    return pd.DataFrame(filas)


def actualidad_estacion(cobertura: pd.DataFrame, hoy=None) -> pd.DataFrame:
    """Tiempo transcurrido desde el último dato de cada estación."""
    hoy = (pd.Timestamp(hoy) if hoy is not None
           else pd.Timestamp.today()).normalize()
    filas = []
    for _, c in cobertura.iterrows():
        fmax = _ts(c["fecha_max"])
        filas.append({"codigo": c["codigo"], "dias_desde": (hoy - fmax).days})
    return pd.DataFrame(filas)


def cobertura_conjunta_estacion(caudales: pd.DataFrame, clima: pd.DataFrame,
                                cobertura: pd.DataFrame,
                                series: dict | None = None) -> pd.DataFrame:
    """Días con caudal y clima simultáneos frente al periodo de solape."""
    series = series if series is not None else _series_caudal(caudales)
    rangos = _rangos_clima(clima)
    fechas_cl = _fechas_clima(clima)
    filas = []
    for _, c in cobertura.iterrows():
        cod = c["codigo"]
        base = {"codigo": cod, "esperados_solape": np.nan,
                "dias_ambos": np.nan, "cobertura_conjunta": np.nan}
        if cod in rangos:
            cmin, cmax = rangos[cod]
            ini = max(_ts(c["fecha_min"]), cmin)
            fin = min(_ts(c["fecha_max"]), cmax)
            if ini <= fin:
                esperados = (fin - ini).days + 1
                idx = series.get(cod, _VACIA).index
                en_solape = idx[(idx >= ini) & (idx <= fin)]
                fset = fechas_cl.get(cod, set())
                dias = int(sum(ts.date() in fset for ts in en_solape)) if fset else 0
                base.update(esperados_solape=esperados, dias_ambos=dias,
                            cobertura_conjunta=dias / esperados * 100
                            if esperados else np.nan)
        filas.append(base)
    return pd.DataFrame(filas)


def complementacion_estacion(caudales: pd.DataFrame, clima: pd.DataFrame,
                             cobertura: pd.DataFrame,
                             clima_inicio: pd.Timestamp = CLIMA_INICIO,
                             series: dict | None = None) -> pd.DataFrame:
    """Brechas de caudal que caen en periodo con clima disponible (≥ 1981).

    Mide qué parte de los vacíos de caudal podría contextualizarse con el
    reanálisis de NASA POWER. Estaciones sin clima → sin valor.
    """
    series = series if series is not None else _series_caudal(caudales)
    cods_clima = set(clima["codigo"].unique()) if not clima.empty else set()
    filas = []
    for _, c in cobertura.iterrows():
        cod = c["codigo"]
        rango = _rango_diario(c["fecha_min"], c["fecha_max"])
        faltan = series.get(cod, _VACIA).reindex(rango).isna()
        total = int(faltan.sum())
        tiene_clima = cod in cods_clima
        if not tiene_clima:
            comp, compl = np.nan, np.nan
        elif total == 0:
            comp, compl = np.nan, 0
        else:
            compl = int((faltan.to_numpy() & (rango >= clima_inicio)).sum())
            comp = compl / total * 100
        filas.append({"codigo": cod, "brechas_total": total,
                      "brechas_complementables": compl, "complementacion": comp})
    return pd.DataFrame(filas)


# --- Orquestadores para la interfaz ----------------------------------------

def resumen_estaciones(datos: dict, hoy=None) -> pd.DataFrame:
    """Una fila por estación con caudal: metadatos + los ocho indicadores."""
    est, caudales = datos["estaciones"], datos["caudales"]
    clima, cob = datos["clima"], datos["cobertura"]
    if cob.empty:
        return pd.DataFrame()

    series = _series_caudal(caudales)  # un solo recorrido, reutilizado abajo

    meta_cols = ["codigo", "nombre", "tipo", "estado", "operador",
                 "cuenca", "aaa", "ala", "lon", "lat"]
    df = (est[[c for c in meta_cols if c in est.columns]]
          .merge(cob[["codigo", "rio", "fecha_min", "fecha_max"]],
                 on="codigo", how="right"))

    comp = completitud_estacion(caudales, cob, series)
    cont = continuidad_estacion(caudales, cob, series)[["codigo", "hueco_max_dias", "n_huecos"]]
    cal = calidad_estacion(caudales, cob, series)[["codigo", "calidad"]]
    act = actualidad_estacion(cob, hoy)
    cc = cobertura_conjunta_estacion(caudales, clima, cob, series)[["codigo", "cobertura_conjunta"]]
    cpl = complementacion_estacion(caudales, clima, cob, series=series)[["codigo", "complementacion"]]

    for parte in (comp, cont, cal, act, cc, cpl):
        df = df.merge(parte, on="codigo", how="left")

    cods_clima = set(clima["codigo"].unique()) if not clima.empty else set()
    df["tiene_clima"] = df["codigo"].isin(cods_clima)
    return df


def resumen_red(datos: dict, resumen: pd.DataFrame | None = None) -> dict:
    """Cifras de red: disponibilidad, cobertura meteo y agregados por estación."""
    disp = disponibilidad(datos["estaciones"], datos["cobertura"], datos["clima"])
    meteo = cobertura_meteo(datos["cobertura"], datos["clima"])
    r = resumen if resumen is not None else resumen_estaciones(datos)

    def _media(col: str) -> float:
        return float(r[col].mean(skipna=True)) if not r.empty and col in r else np.nan

    return {
        **disp,
        "meteo_ratio": meteo["ratio"],
        "con_ambos": meteo["con_ambos"],
        "completitud_media": _media("completitud"),
        "hueco_mediano": (float(r["hueco_max_dias"].median())
                          if not r.empty else np.nan),
        "calidad_media": _media("calidad"),
        "actualidad_mediana_dias": (float(r["dias_desde"].median())
                                    if not r.empty else np.nan),
        "cobertura_conjunta_media": _media("cobertura_conjunta"),
        "complementacion_media": _media("complementacion"),
    }
