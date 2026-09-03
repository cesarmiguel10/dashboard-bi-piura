@echo off
REM ============================================================
REM  Version HEADLESS para la Tarea Programada de Windows.
REM  Actualiza los datos (SNIRH + NASA POWER) y los sube a GitHub;
REM  Streamlit Cloud se redepliega solo. Sin pausas ni ventanas.
REM  (El boton manual de doble clic sigue siendo actualizar_tablero.bat.)
REM  Deja rastro en actualizar.log para revisar si algo falla de noche.
REM ============================================================
cd /d "D:\DASHBOAR BI"

echo [%date% %time%] === Actualizando datos de Piura ===>> actualizar.log
".venv\Scripts\python.exe" actualizar.py >> actualizar.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR al actualizar: no se sube nada.>> actualizar.log
  exit /b 1
)

git add data
git commit -m "Actualizacion automatica de datos de Piura" >> actualizar.log 2>&1 || echo [%date% %time%] Sin cambios: nada que subir.>> actualizar.log
git push >> actualizar.log 2>&1
echo [%date% %time%] === Listo ===>> actualizar.log
