"""Análisis estadístico: correlaciones caudal ↔ clima y desfase temporal (lag)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib.carga import VARIABLES


def _corr(a: pd.Series, b: pd.Series, metodo: str) -> tuple[float, int]:
    """Correlación entre dos series alineadas, ignorando faltantes."""
    d = pd.concat([a, b], axis=1).dropna()
    if len(d) < 6:
        return (np.nan, len(d))
    r = d.iloc[:, 0].corr(d.iloc[:, 1], method=metodo)
    return (float(r), len(d))


def correlaciones(df: pd.DataFrame, metodo: str = "pearson") -> pd.DataFrame:
    """Correlación de 'caudal' contra cada variable climática disponible."""
    filas = []
    if "caudal" not in df.columns:
        return pd.DataFrame(columns=["variable", "etiqueta", "r", "n"])
    for v, (etq, unidad, _) in VARIABLES.items():
        if v not in df.columns:
            continue
        r, n = _corr(df["caudal"], df[v], metodo)
        filas.append({"variable": v, "etiqueta": f"{etq} ({unidad})", "r": r, "n": n})
    return pd.DataFrame(filas)


def correlacion_por_lag(caudal: pd.Series, var: pd.Series,
                        max_lag: int = 6, metodo: str = "pearson") -> pd.DataFrame:
    """Correlación caudal vs. variable desfasada k periodos (var adelanta al caudal).

    lag > 0 significa que la variable de hace k meses se compara con el caudal
    actual (p. ej. la lluvia previa que alimenta el caudal).
    """
    filas = []
    for k in range(0, max_lag + 1):
        r, n = _corr(caudal, var.shift(k), metodo)
        filas.append({"lag": k, "r": r, "n": n})
    return pd.DataFrame(filas)


def mejor_lag(caudal: pd.Series, var: pd.Series, max_lag: int = 6,
              metodo: str = "pearson") -> dict:
    tabla = correlacion_por_lag(caudal, var, max_lag, metodo)
    val = tabla.dropna(subset=["r"])
    if val.empty:
        return {"lag": 0, "r": np.nan, "n": 0}
    fila = val.loc[val["r"].abs().idxmax()]
    return {"lag": int(fila["lag"]), "r": float(fila["r"]), "n": int(fila["n"])}
