# Dashboard BI — Caudales vs. Clima (Región Piura)

Explora la **relación entre los caudales** de las estaciones hidrométricas del
departamento de **Piura** (SNIRH / ANA) y variables **climáticas** (temperatura,
precipitación y viento) de **NASA POWER**, con un mapa que **pinta la zona de
Piura** y muestra cada estación.

## Fuentes de datos

- **Caudales:** SNIRH – ANA · `https://snirh.ana.gob.pe/visorPorCuenca/?IdVar=263`
  (endpoints `ListarMapaGEO`, `ListarInfoGEO`, `CaudalSerie`). Cada estación trae
  su promedio histórico y los **últimos ~5 años hidrológicos** diarios (el año
  hidrológico peruano empieza el 1 de septiembre).
- **Clima:** NASA POWER · `https://power.larc.nasa.gov` (API REST, diaria, desde
  1981). Parámetros `T2M`, `PRECTOTCORR`, `WS2M`.
- **Límite de Piura:** GeoJSON público de departamentos del Perú (se cachea en
  `data/piura.geojson`). Sirve para **filtrar** las estaciones que caen dentro de
  Piura y para **pintar la zona** en el mapa.

Todas las fuentes son públicas; no se necesitan credenciales.

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell/CMD)
pip install -r requirements.txt
```

## 1) Datos (descarga y cache)

Un solo comando baja todo lo de Piura (inventario → caudales → clima) y guarda la
fecha de actualización:

```bash
python actualizar.py
```

Filtra el inventario nacional al **polígono de Piura** y solo entonces descarga las
series (~63 estaciones · ~51 con caudal · ~46 comparables con clima). Salidas en
`data/`: `estaciones.parquet`, `caudales_diarios.parquet`,
`caudal_climatologia.parquet`, `cobertura.parquet`, `clima_diario.parquet`,
`piura.geojson`, `ultima_actualizacion.txt`.

## 2) Actualización automática

Cada corrida de `actualizar.py` trae los **datos nuevos** que hayan publicado el
SNIRH y NASA POWER, así el tablero se pone al día con el futuro. Hay tres formas:

- **A mano:** `python actualizar.py`.
- **Desde el tablero:** botón **«🔄 Actualizar ahora»** (barra lateral). Muestra
  también la fecha de la última actualización.
- **Sola, sin abrir la app (recomendado):** una **Tarea Programada de Windows**
  que corre diario a las 07:00 y al iniciar sesión. Regístrala una sola vez:

  ```powershell
  powershell -ExecutionPolicy Bypass -File "D:\DASHBOAR BI\registrar_tarea.ps1"
  ```

  Si diera «Acceso denegado», abre PowerShell **como administrador** y repite.
  Para probarla al instante: `Start-ScheduledTask -TaskName "DashboardBI Piura - Actualizar datos"`.

## 3) Dashboard

```bash
streamlit run app.py
```

- **Mapa** con la **zona de Piura pintada** y las estaciones (color por estado;
  tamaño según tenga serie), encuadrado a la región.
- **Selección** por mapa o buscador; filtros por **cuenca**, **sub-zona (ALA)**,
  estado y solape con clima.
- **Series** caudal vs. cada variable (doble eje) y **dispersión** con tendencia.
- **Correlación** Pearson/Spearman y **desfase temporal (lag)** mensual, con una
  conclusión en lenguaje simple.

## Notas

- La correlación solo aplica donde el caudal se **solapa** con NASA POWER (≥1981).
- El ETL descarga con pausas y reintentos para no sobrecargar los servidores.
- `data/` no se versiona (ver `.gitignore`).
- Para cambiar de región, `lib/geo.py` (`REGION`) y `--region` en el ETL.
