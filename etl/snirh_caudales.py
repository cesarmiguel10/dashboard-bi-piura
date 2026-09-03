"""ETL 2 — Series de caudal por estación (SNIRH/ANA).

`Principal.asmx/CaudalSerie` devuelve, por estación:
  - "Prom. Histórico": climatología diaria (día del año hidrológico, 1-sep..31-ago).
  - Un serie por año hidrológico ("AAAA-AAAA"): los últimos ~5 años, diarios.

El año hidrológico peruano arranca el 1 de septiembre; el índice i de cada
serie anual "A-B" corresponde a la fecha date(A, 9, 1) + i días.

Uso:
    python -m etl.snirh_caudales               # usa data/estaciones.parquet
    python -m etl.snirh_caudales --limit 30
"""
from __future__ import annotations

import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd

from etl.common import DATA, Sesion, snirh

_RE_ANIO = re.compile(r"^(\d{4})\s*-\s*(\d{4})$")
_RE_RIO = re.compile(r"-\s*(R[íi]o\s+.+)$")
PROM_HISTORICO = "Prom. Histórico"


def _rio_de_titulo(titulo: str) -> str | None:
    m = _RE_RIO.search(titulo or "")
    return m.group(1).strip() if m else None


def serie_estacion(sesion: Sesion, codigo: str, operador: int) -> dict | None:
    """Devuelve dict con 'diario' (list[fecha,caudal]), 'climatologia' y meta."""
    payload = {"pIdEstacion": int(codigo), "pIdOperador": int(operador)}
    data = snirh(sesion, "Principal.asmx", "CaudalSerie", payload)
    if not isinstance(data, list) or not data:
        return None
    cfg = data[0]
    series = cfg.get("series") or []
    if not series:
        return None

    diario: list[tuple[date, float]] = []
    climatologia: list[tuple[int, float]] = []
    for s in series:
        nombre = (s.get("name") or "").strip()
        valores = s.get("data") or []
        if nombre == PROM_HISTORICO:
            for i, v in enumerate(valores):
                if v is not None:
                    climatologia.append((i, float(v)))
            continue
        m = _RE_ANIO.match(nombre)
        if not m:
            continue
        inicio = date(int(m.group(1)), 9, 1)
        for i, v in enumerate(valores):
            if v is not None:
                diario.append((inicio + timedelta(days=i), float(v)))

    return {
        "codigo": codigo,
        "rio": _rio_de_titulo(cfg.get("title", "")),
        "diario": diario,
        "climatologia": climatologia,
    }


def descargar_todas(sesion: Sesion, est: pd.DataFrame, workers: int = 6):
    est = est[est["operador"].notna()].reset_index(drop=True)
    total = len(est)
    diarios, climas, cobertura = [], [], []

    def tarea(row):
        return serie_estacion(sesion, row["codigo"], int(row["operador"]))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(tarea, r): r["codigo"] for _, r in est.iterrows()}
        hechos = 0
        for fut in as_completed(futs):
            cod = futs[fut]
            hechos += 1
            try:
                res = fut.result()
            except Exception:
                res = None
            if hechos % 50 == 0 or hechos == total:
                print(f"  caudales {hechos}/{total}")
            if not res or not res["diario"]:
                continue
            for f, v in res["diario"]:
                diarios.append((cod, f, v))
            for d, v in res["climatologia"]:
                climas.append((cod, d, v))
            fechas = [f for f, _ in res["diario"]]
            cobertura.append({
                "codigo": cod,
                "rio": res["rio"],
                "fecha_min": min(fechas),
                "fecha_max": max(fechas),
                "n_dias": len(fechas),
                "anios": sorted({f.year for f in fechas}),
            })

    df_diario = pd.DataFrame(diarios, columns=["codigo", "fecha", "caudal"])
    if not df_diario.empty:
        df_diario["fecha"] = pd.to_datetime(df_diario["fecha"])
    df_clima = pd.DataFrame(climas, columns=["codigo", "dia_hidro", "caudal_prom"])
    df_cob = pd.DataFrame(cobertura)
    return df_diario, df_clima, df_cob


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    est = pd.read_parquet(DATA / "estaciones.parquet")
    if args.limit:
        est = est[est["operador"].notna()].head(args.limit)

    sesion = Sesion(intervalo_min=0.2)
    print(f"Descargando caudales de {int(est['operador'].notna().sum())} estaciones…")
    df_diario, df_clima, df_cob = descargar_todas(sesion, est)

    df_diario.to_parquet(DATA / "caudales_diarios.parquet", index=False)
    df_clima.to_parquet(DATA / "caudal_climatologia.parquet", index=False)
    df_cob.to_parquet(DATA / "cobertura.parquet", index=False)
    print(f"  {len(df_cob)} estaciones con datos, "
          f"{len(df_diario):,} registros diarios de caudal")
    print(f"Guardado en {DATA}")


if __name__ == "__main__":
    main()
