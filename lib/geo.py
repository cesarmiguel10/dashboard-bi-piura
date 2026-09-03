"""Región de interés (Piura): límite del departamento y filtro geográfico.

Descarga una sola vez el polígono del departamento (GeoJSON público de límites
departamentales del Perú), lo cachea en `data/piura.geojson`, y ofrece un test
punto-en-polígono sin dependencias extra (algoritmo de rayo / ray casting).

El mismo polígono se usa para dos cosas:
  - filtrar las estaciones que caen dentro de Piura (ETL y app),
  - pintar la zona en el mapa (app).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parent.parent / "data"

# Departamento a enfocar. La fuente es pública (límites departamentales del Perú).
REGION = "PIURA"
_ARCHIVO = DATA / "piura.geojson"
_FUENTE = ("https://raw.githubusercontent.com/juaneladio/peru-geojson/"
           "master/peru_departamental_simple.geojson")


def descargar_region(nombre: str = REGION) -> dict:
    """Descarga el límite del departamento y lo guarda como Feature en `data/`."""
    r = requests.get(_FUENTE, timeout=60)
    r.raise_for_status()
    gj = r.json()
    feat = next(
        (f for f in gj["features"]
         if str(f["properties"].get("NOMBDEP", "")).upper() == nombre.upper()),
        None)
    if feat is None:
        raise ValueError(f"No se encontró el departamento {nombre!r} en la fuente.")
    DATA.mkdir(exist_ok=True)
    _ARCHIVO.write_text(json.dumps(feat, ensure_ascii=False), encoding="utf-8")
    return feat


def region_feature(nombre: str = REGION, refrescar: bool = False) -> dict:
    """Devuelve el Feature del departamento (de la caché; lo descarga si falta)."""
    if refrescar or not _ARCHIVO.exists():
        return descargar_region(nombre)
    return json.loads(_ARCHIVO.read_text(encoding="utf-8"))


def geometria(nombre: str = REGION) -> dict:
    """Geometría (Polygon/MultiPolygon) del departamento."""
    return region_feature(nombre)["geometry"]


def _en_anillo(x: float, y: float, anillo) -> bool:
    """True si el punto (x, y) cae dentro del anillo (lista de [lon, lat])."""
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            dentro = not dentro
        j = i
    return dentro


def dentro(lon: float, lat: float, geom: dict | None = None) -> bool:
    """True si el punto (lon, lat) cae dentro de la geometría, respetando huecos."""
    if lon is None or lat is None or pd.isna(lon) or pd.isna(lat):
        return False
    if geom is None:
        geom = geometria()
    polis = ([geom["coordinates"]] if geom["type"] == "Polygon"
             else geom["coordinates"])
    for poli in polis:
        if _en_anillo(lon, lat, poli[0]) and not any(
                _en_anillo(lon, lat, poli[k]) for k in range(1, len(poli))):
            return True
    return False


def filtrar(df: pd.DataFrame, geom: dict | None = None) -> pd.DataFrame:
    """Devuelve solo las filas cuyo (lon, lat) cae dentro de la región."""
    if df.empty:
        return df
    if geom is None:
        geom = geometria()
    mask = [dentro(lo, la, geom) for lo, la in zip(df["lon"], df["lat"])]
    return df[pd.Series(mask, index=df.index)].reset_index(drop=True)
