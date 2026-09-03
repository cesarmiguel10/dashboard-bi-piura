"""ETL 3 — Variables climáticas por estación (NASA POWER).

Para cada estación con caudal que se solape con la cobertura de NASA POWER
(>= 1981) descarga temperatura (T2M), precipitación (PRECTOTCORR) y viento
a 2 m (WS2M) en su punto (lat/lon), en el mismo rango de fechas del caudal.

Uso:
    python -m etl.nasa_power
    python -m etl.nasa_power --limit 30
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import pandas as pd

from etl.common import DATA, NASA_INICIO_MINIMO, NASA_PARAMS, Sesion, nasa_power_diario

_FALTANTE = -999.0
_INICIO_MIN = pd.Timestamp(NASA_INICIO_MINIMO)


def _clima_estacion(sesion: Sesion, codigo: str, lat: float, lon: float,
                    inicio: pd.Timestamp, fin: pd.Timestamp) -> pd.DataFrame:
    params = nasa_power_diario(
        sesion, lat, lon,
        inicio.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d"), NASA_PARAMS,
    )
    fechas = sorted(params[NASA_PARAMS[0]].keys())
    filas = []
    for f in fechas:
        fila = {"codigo": codigo, "fecha": pd.to_datetime(f, format="%Y%m%d")}
        for p in NASA_PARAMS:
            v = params.get(p, {}).get(f)
            fila[p.lower()] = None if v is None or v == _FALTANTE else float(v)
        filas.append(fila)
    return pd.DataFrame(filas)


def descargar(sesion: Sesion, est: pd.DataFrame, cob: pd.DataFrame,
              workers: int = 4) -> pd.DataFrame:
    hoy = pd.Timestamp(date.today())
    coords = est.set_index("codigo")[["lat", "lon"]]
    trabajos = []
    for _, r in cob.iterrows():
        fmax = pd.Timestamp(r["fecha_max"])
        if fmax < _INICIO_MIN:  # sin solape con NASA POWER
            continue
        cod = r["codigo"]
        if cod not in coords.index:
            continue
        lat, lon = coords.loc[cod, "lat"], coords.loc[cod, "lon"]
        if pd.isna(lat) or pd.isna(lon):
            continue
        inicio = max(pd.Timestamp(r["fecha_min"]), _INICIO_MIN)
        fin = min(fmax, hoy)
        trabajos.append((cod, float(lat), float(lon), inicio, fin))

    total = len(trabajos)
    print(f"  {total} estaciones con solape (>= {NASA_INICIO_MINIMO})")
    partes = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_clima_estacion, sesion, *t): t[0] for t in trabajos}
        hechos = 0
        for fut in as_completed(futs):
            hechos += 1
            try:
                partes.append(fut.result())
            except Exception as e:
                print(f"    fallo {futs[fut]}: {e!r}")
            if hechos % 25 == 0 or hechos == total:
                print(f"  clima {hechos}/{total}")
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    est = pd.read_parquet(DATA / "estaciones.parquet")
    cob = pd.read_parquet(DATA / "cobertura.parquet")
    if args.limit:
        cob = cob.head(args.limit)

    sesion = Sesion(intervalo_min=0.3)  # NASA POWER: ritmo prudente
    print("Descargando clima (NASA POWER)…")
    df = descargar(sesion, est, cob)
    if df.empty:
        print("Sin datos de clima.")
        return
    df.to_parquet(DATA / "clima_diario.parquet", index=False)
    print(f"  {df['codigo'].nunique()} estaciones, {len(df):,} registros diarios")
    print(f"Guardado: {DATA / 'clima_diario.parquet'}")


if __name__ == "__main__":
    main()
