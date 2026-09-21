"""Pruebas de los indicadores de línea base (datos sintéticos, sin parquet)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from lib import indicadores as ind


def _caudal(codigo: str, fechas, valores=None) -> pd.DataFrame:
    fechas = pd.to_datetime(fechas)
    if valores is None:
        valores = [1.0] * len(fechas)
    return pd.DataFrame({"codigo": codigo, "fecha": fechas, "caudal": valores})


def _cob(codigo, fmin, fmax, n_dias) -> dict:
    return {"codigo": codigo, "rio": "Río X", "fecha_min": fmin,
            "fecha_max": fmax, "n_dias": n_dias, "anios": [fmin.year]}


# --- helper de rachas -------------------------------------------------------

def test_mayor_tramo_nan_cuenta_racha_mas_larga():
    mask = pd.Series([False, True, True, False, True, False])
    assert ind._mayor_tramo_nan(mask) == (2, 2)


def test_mayor_tramo_nan_sin_faltantes():
    assert ind._mayor_tramo_nan(pd.Series([False, False, False])) == (0, 0)


# --- estación con un hueco de 5 días ---------------------------------------

def _estacion_con_hueco():
    todo = pd.date_range("2020-01-01", "2020-01-31", freq="D")
    falta = pd.date_range("2020-01-10", "2020-01-14", freq="D")  # 5 días
    presentes = todo.difference(falta)
    caudales = _caudal("A", presentes)
    cob = pd.DataFrame([_cob("A", dt.date(2020, 1, 1), dt.date(2020, 1, 31),
                             len(presentes))])
    return caudales, cob


def test_completitud_con_hueco():
    caudales, cob = _estacion_con_hueco()
    fila = ind.completitud_estacion(caudales, cob).iloc[0]
    assert fila["esperados"] == 31
    assert fila["validos"] == 26
    assert fila["completitud"] == 26 / 31 * 100


def test_continuidad_detecta_mayor_hueco():
    caudales, cob = _estacion_con_hueco()
    fila = ind.continuidad_estacion(caudales, cob).iloc[0]
    assert fila["hueco_max_dias"] == 5
    assert fila["n_huecos"] == 1


def test_calidad_descarta_valores_negativos():
    fechas = pd.date_range("2020-01-01", "2020-01-04", freq="D")
    caudales = _caudal("A", fechas, [1.0, -3.0, 2.0, 4.0])  # uno inválido
    cob = pd.DataFrame([_cob("A", dt.date(2020, 1, 1), dt.date(2020, 1, 4), 4)])
    fila = ind.calidad_estacion(caudales, cob).iloc[0]
    assert fila["disponibles"] == 4
    assert fila["validos_control"] == 3
    assert fila["calidad"] == 75.0


def test_actualidad_usa_hoy_fijo():
    cob = pd.DataFrame([_cob("A", dt.date(2020, 1, 1), dt.date(2020, 1, 31), 31)])
    fila = ind.actualidad_estacion(cob, hoy="2020-02-10").iloc[0]
    assert fila["dias_desde"] == 10


def test_completitud_rango_de_un_dia():
    caudales = _caudal("A", ["2020-01-01"])
    cob = pd.DataFrame([_cob("A", dt.date(2020, 1, 1), dt.date(2020, 1, 1), 1)])
    fila = ind.completitud_estacion(caudales, cob).iloc[0]
    assert fila["esperados"] == 1
    assert fila["completitud"] == 100.0


# --- complementación y cobertura conjunta ----------------------------------

def test_complementacion_excluye_brechas_previas_a_1981():
    # Rango 1980-12-30 … 1981-01-03 (5 días); solo 2 con dato → 3 brechas.
    caudales = _caudal("C", ["1980-12-30", "1981-01-03"])
    cob = pd.DataFrame([_cob("C", dt.date(1980, 12, 30), dt.date(1981, 1, 3), 2)])
    clima = pd.DataFrame({"codigo": "C",
                          "fecha": pd.to_datetime(["1981-01-01", "1981-01-02"]),
                          "t2m": [20.0, 21.0], "prectotcorr": [0.0, 1.0],
                          "ws2m": [2.0, 2.0]})
    fila = ind.complementacion_estacion(caudales, clima, cob).iloc[0]
    assert fila["brechas_total"] == 3
    # Solo 1981-01-01 y 1981-01-02 son complementables (1980-12-31 queda fuera).
    assert fila["brechas_complementables"] == 2


def test_indicadores_sin_clima_son_nan():
    caudales = _caudal("B", pd.date_range("2020-01-01", "2020-01-10", freq="D"))
    cob = pd.DataFrame([_cob("B", dt.date(2020, 1, 1), dt.date(2020, 1, 10), 10)])
    clima = pd.DataFrame(columns=["codigo", "fecha", "t2m", "prectotcorr", "ws2m"])
    cc = ind.cobertura_conjunta_estacion(caudales, clima, cob).iloc[0]
    cpl = ind.complementacion_estacion(caudales, clima, cob).iloc[0]
    assert pd.isna(cc["cobertura_conjunta"])
    assert pd.isna(cpl["complementacion"])


# --- nivel de red -----------------------------------------------------------

def test_disponibilidad_y_cobertura_meteo():
    est = pd.DataFrame({"codigo": ["A", "B", "C", "D"]})
    cob = pd.DataFrame([_cob("A", dt.date(2020, 1, 1), dt.date(2020, 1, 2), 2),
                        _cob("B", dt.date(2020, 1, 1), dt.date(2020, 1, 2), 2),
                        _cob("C", dt.date(2020, 1, 1), dt.date(2020, 1, 2), 2)])
    clima = pd.DataFrame({"codigo": ["C"], "fecha": pd.to_datetime(["2020-01-01"]),
                          "t2m": [20.0], "prectotcorr": [0.0], "ws2m": [2.0]})
    disp = ind.disponibilidad(est, cob, clima)
    assert disp["total"] == 4 and disp["con_caudal"] == 3 and disp["con_clima"] == 1
    assert disp["disp_caudal"] == 3 / 4 * 100
    meteo = ind.cobertura_meteo(cob, clima)
    assert meteo["con_ambos"] == 1 and meteo["ratio"] == 1 / 3 * 100
