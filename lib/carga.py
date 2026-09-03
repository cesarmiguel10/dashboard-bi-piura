"""Carga de datasets y uniones caudal ↔ clima (funciones puras, sin Streamlit)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

# Variables climáticas: columna -> (etiqueta, unidad, agregación mensual)
VARIABLES = {
    "t2m": ("Temperatura", "°C", "mean"),
    "prectotcorr": ("Precipitación", "mm/día", "sum"),
    "ws2m": ("Viento (2 m)", "m/s", "mean"),
}


def leer(nombre: str) -> pd.DataFrame:
    ruta = DATA / nombre
    return pd.read_parquet(ruta) if ruta.exists() else pd.DataFrame()


def cargar_todo() -> dict[str, pd.DataFrame]:
    return {
        "estaciones": leer("estaciones.parquet"),
        "caudales": leer("caudales_diarios.parquet"),
        "clima": leer("clima_diario.parquet"),
        "cobertura": leer("cobertura.parquet"),
    }


def serie_estacion(caudales: pd.DataFrame, clima: pd.DataFrame,
                   codigo: str) -> pd.DataFrame:
    """Une caudal y clima diarios de una estación por fecha."""
    q = caudales[caudales["codigo"] == codigo][["fecha", "caudal"]]
    if q.empty:
        return pd.DataFrame()
    c = clima[clima["codigo"] == codigo] if not clima.empty else pd.DataFrame()
    cols = ["fecha"] + [v for v in VARIABLES if not c.empty and v in c.columns]
    df = q.merge(c[cols], on="fecha", how="left") if not c.empty else q.copy()
    return df.sort_values("fecha").reset_index(drop=True)


def agregar_mensual(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega a mensual: caudal promedio, clima según su regla (media/suma)."""
    if df.empty:
        return df
    g = df.set_index("fecha")
    reglas = {"caudal": "mean"}
    for v, (_, _, agg) in VARIABLES.items():
        if v in g.columns:
            reglas[v] = agg
    men = g.resample("MS").agg(reglas)
    # Un mes con demasiados días faltantes de caudal no es representativo.
    validos = g["caudal"].resample("MS").count()
    men.loc[validos < 15, "caudal"] = pd.NA
    return men.reset_index()
