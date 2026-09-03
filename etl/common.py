"""Utilidades compartidas del ETL: rutas, sesión HTTP con reintentos y
rate-limit, y clientes de bajo nivel para SNIRH (ANA) y NASA POWER.

Ambas fuentes son públicas; no se requieren credenciales. Se descarga con
pausas y reintentos para no sobrecargar los servidores de origen.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Rutas del proyecto -----------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
DATA.mkdir(exist_ok=True)

# --- Endpoints --------------------------------------------------------------
SNIRH_BASE = "https://snirh.ana.gob.pe/visorPorCuenca"
NASA_POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Capa de estaciones hidrométricas (variable caudal) en el visor.
CAPA_HIDROMETRICA = 263

# Parámetros NASA POWER: temperatura, precipitación y viento a 2 m.
NASA_PARAMS = ["T2M", "PRECTOTCORR", "WS2M"]
NASA_INICIO_MINIMO = "1981-01-01"  # NASA POWER no tiene datos previos.

_UA = "Mozilla/5.0 (DashboardBI-ANA-NASA; contacto: uso academico)"


class Sesion:
    """Sesión HTTP con reintentos automáticos y rate-limit por dominio."""

    def __init__(self, intervalo_min: float = 0.25):
        self._intervalo = intervalo_min
        self._ultimo = 0.0
        self._lock = threading.Lock()
        self.s = requests.Session()
        reintentos = Retry(
            total=4,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        adapter = HTTPAdapter(max_retries=reintentos, pool_maxsize=16)
        self.s.mount("https://", adapter)
        self.s.headers.update({"User-Agent": _UA})

    def _esperar(self) -> None:
        with self._lock:
            delta = time.monotonic() - self._ultimo
            if delta < self._intervalo:
                time.sleep(self._intervalo - delta)
            self._ultimo = time.monotonic()

    def post_json(self, url: str, payload: dict, timeout: int = 45) -> Any:
        self._esperar()
        r = self.s.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json; charset=UTF-8"},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()

    def get_json(self, url: str, params: dict, timeout: int = 60) -> Any:
        self._esperar()
        r = self.s.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()


def snirh(sesion: Sesion, servicio: str, metodo: str, payload: dict) -> Any:
    """Llama a un método ASMX del SNIRH y devuelve el contenido de `.d`.

    `.d` viene como cadena JSON (o texto); se intenta parsear a objeto.
    servicio: 'ServicioGeneral.asmx' o 'Principal.asmx'.
    """
    url = f"{SNIRH_BASE}/{servicio}/{metodo}"
    data = sesion.post_json(url, payload)
    d = data.get("d") if isinstance(data, dict) else data
    if isinstance(d, str):
        try:
            return json.loads(d)
        except (json.JSONDecodeError, TypeError):
            return d
    return d


def nasa_power_diario(sesion: Sesion, lat: float, lon: float,
                      inicio: str, fin: str,
                      params: list[str] | None = None) -> dict:
    """Descarga series diarias de NASA POWER para un punto.

    inicio/fin en formato 'YYYY-MM-DD'. Devuelve el dict de parámetros
    {PARAM: {YYYYMMDD: valor}}. Los valores -999 significan faltante.
    """
    params = params or NASA_PARAMS
    q = {
        "parameters": ",".join(params),
        "community": "AG",
        "longitude": round(float(lon), 4),
        "latitude": round(float(lat), 4),
        "start": inicio.replace("-", ""),
        "end": fin.replace("-", ""),
        "format": "JSON",
    }
    j = sesion.get_json(NASA_POWER, q)
    return j["properties"]["parameter"]
