"""Actualiza todos los datos de Piura y registra la fecha de actualización.

Corre los 3 ETL en orden (inventario → caudales → clima) y guarda un sello en
`data/ultima_actualizacion.txt`. Cada corrida trae los datos nuevos que hayan
publicado el SNIRH (caudales) y NASA POWER (clima), así el tablero se pone al día.

Se usa desde tres lados:
  - a mano:            python actualizar.py
  - botón del tablero: "🔄 Actualizar ahora"
  - tarea programada:  Programador de tareas de Windows (diaria + al iniciar sesión)
"""
from __future__ import annotations

from datetime import datetime

from etl import nasa_power, snirh_caudales, snirh_estaciones
from etl.common import DATA

SELLO = DATA / "ultima_actualizacion.txt"


def actualizar() -> str:
    print("== 1/3 Inventario de estaciones (Piura) ==")
    snirh_estaciones.main()
    print("== 2/3 Caudales (SNIRH/ANA) ==")
    snirh_caudales.main()
    print("== 3/3 Clima (NASA POWER) ==")
    nasa_power.main()

    sello = datetime.now().strftime("%Y-%m-%d %H:%M")
    SELLO.write_text(sello, encoding="utf-8")
    print(f"== LISTO: datos actualizados {sello} ==")
    return sello


if __name__ == "__main__":
    actualizar()
