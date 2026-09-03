"""ETL 1 — Inventario nacional de estaciones hidrométricas (SNIRH/ANA).

Descarga las estaciones (código, nombre, estado, lat/lon) y, por cada una,
el IDOperador necesario para pedir su serie de caudal.

Uso:
    python -m etl.snirh_estaciones            # todas
    python -m etl.snirh_estaciones --limit 30 # subconjunto para validar
"""
from __future__ import annotations

import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from etl.common import CAPA_HIDROMETRICA, DATA, Sesion, snirh
from lib import geo

# El ícono codifica tipo (convencional/automática) y estado.
_ESTADOS = {"funciona": "Funcionando", "paralizada": "Paralizada", "cerrado": "Cerrada"}

_RE_OPERADOR = re.compile(r"IDOperador\s*:\s*(\d+)")
_RE_CUENCA = re.compile(r"Unid\. Hidrogr[^<]*</div>\s*<div[^>]*>([^<]+)</div>")
_RE_AAA = re.compile(r">AAA</span>\s*:\s*([^<]+)</div>")
_RE_ALA = re.compile(r">ALA</span>\s*:\s*([^<]+)</div>")


def _texto(m) -> str | None:
    return m.group(1).strip() if m else None


def _parse_icono(icono: str) -> tuple[str, str]:
    """'est_conven_funciona' -> ('Convencional', 'Funcionando')."""
    tipo = "Automática" if "auto" in icono else "Convencional"
    estado = next((v for k, v in _ESTADOS.items() if k in icono), "Desconocido")
    return tipo, estado


def descargar_inventario(sesion: Sesion) -> pd.DataFrame:
    """Devuelve un DataFrame con las estaciones (sin operador todavía)."""
    payload = {
        "pIDMapa": CAPA_HIDROMETRICA,
        "CodigoUH": "0",  # 0 = nivel nacional
        "pParametros": "<Registro><Buscar></Buscar></Registro>",
        "pIdModulo": 0,
    }
    items = snirh(sesion, "ServicioGeneral.asmx", "ListarMapaGEO", payload)
    filas = []
    for it in items:
        # El primer item es configuración de estilo (sin 'I'); se ignora.
        if not isinstance(it, dict) or "I" not in it:
            continue
        coord = it.get("C") or [None, None]
        tipo, estado = _parse_icono(it.get("O", ""))
        filas.append({
            "codigo": str(it["I"]),
            "nombre": it.get("D", "").strip(),
            "tipo": tipo,
            "estado": estado,
            "icono": it.get("O", ""),
            "lon": coord[0],
            "lat": coord[1],
        })
    df = pd.DataFrame(filas).drop_duplicates("codigo").reset_index(drop=True)
    return df


def _info_de(sesion: Sesion, codigo: str) -> dict:
    """ListarInfoGEO por estación: operador + cuenca + AAA + ALA."""
    payload = {"pIDMapa": CAPA_HIDROMETRICA, "CodigoUH": "0",
               "IDRegistro": codigo, "pIdModulo": 0}
    html = snirh(sesion, "ServicioGeneral.asmx", "ListarInfoGEO", payload)
    if not isinstance(html, str):
        return {"operador": None, "cuenca": None, "aaa": None, "ala": None}
    op = _RE_OPERADOR.search(html)
    return {
        "operador": int(op.group(1)) if op else None,
        "cuenca": _texto(_RE_CUENCA.search(html)),
        "aaa": _texto(_RE_AAA.search(html)),
        "ala": _texto(_RE_ALA.search(html)),
    }


def completar_info(sesion: Sesion, df: pd.DataFrame,
                   workers: int = 6) -> pd.DataFrame:
    """Agrega operador, cuenca, AAA y ALA consultando ListarInfoGEO por estación."""
    info: dict[str, dict] = {}
    total = len(df)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_info_de, sesion, c): c for c in df["codigo"]}
        hechos = 0
        for fut in as_completed(futs):
            cod = futs[fut]
            try:
                info[cod] = fut.result()
            except Exception:
                info[cod] = {"operador": None, "cuenca": None,
                             "aaa": None, "ala": None}
            hechos += 1
            if hechos % 50 == 0 or hechos == total:
                print(f"  info {hechos}/{total}")
    df = df.copy()
    df["operador"] = df["codigo"].map(lambda c: info[c]["operador"]).astype("Int64")
    df["cuenca"] = df["codigo"].map(lambda c: info[c]["cuenca"])
    df["aaa"] = df["codigo"].map(lambda c: info[c]["aaa"])
    df["ala"] = df["codigo"].map(lambda c: info[c]["ala"])
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="limitar nº de estaciones")
    ap.add_argument("--solo-funciona", action="store_true",
                    help="quedarse solo con estaciones en funcionamiento")
    ap.add_argument("--region", default=geo.REGION,
                    help="departamento a enfocar (por defecto, Piura)")
    args = ap.parse_args()

    sesion = Sesion(intervalo_min=0.2)
    print("Descargando inventario nacional…")
    df = descargar_inventario(sesion)
    print(f"  {len(df)} estaciones ({df['estado'].value_counts().to_dict()})")

    # Enfocar en la región de interés: solo las estaciones dentro del polígono
    # del departamento. Así el ETL siguiente (caudales y clima) queda acotado.
    geom = geo.geometria(args.region)
    df = geo.filtrar(df, geom)
    print(f"  {len(df)} dentro de {args.region.title()}")

    if args.solo_funciona:
        df = df[df["estado"] == "Funcionando"].reset_index(drop=True)
        print(f"  filtrado a {len(df)} en funcionamiento")
    if args.limit:
        df = df.head(args.limit).reset_index(drop=True)
        print(f"  limitado a {len(df)}")

    print("Consultando info por estación (operador, cuenca, AAA, ALA)…")
    df = completar_info(sesion, df)
    con_op = int(df["operador"].notna().sum())
    con_cuenca = int(df["cuenca"].notna().sum())
    print(f"  {con_op}/{len(df)} con operador · {con_cuenca}/{len(df)} con cuenca")

    salida = DATA / "estaciones.parquet"
    df.to_parquet(salida, index=False)
    print(f"Guardado: {salida}")


if __name__ == "__main__":
    main()
