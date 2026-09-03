@echo off
REM ============================================================
REM  BOTON: Actualizar el tablero de Piura (doble clic aqui).
REM  1) Baja datos nuevos del SNIRH y NASA POWER.
REM  2) Los sube a GitHub -> Streamlit Cloud se redepliega solo.
REM  Resultado en 1-2 min:  https://dashboard-bi-piura.streamlit.app/
REM ============================================================
cd /d "D:\DASHBOAR BI"

echo.
echo === 1/2  Actualizando datos de Piura (SNIRH + NASA POWER)... ===
".venv\Scripts\python.exe" actualizar.py
if errorlevel 1 (
  echo.
  echo *** Hubo un error al actualizar los datos. Revisa el mensaje de arriba. ***
  pause
  exit /b 1
)

echo.
echo === 2/2  Subiendo a GitHub (Streamlit se redepliega solo)... ===
git add -A
git commit -m "Actualizar datos de Piura" || echo (Sin cambios nuevos: no habia nada que subir.)
git push

echo.
echo ============================================================
echo  LISTO. En 1-2 minutos el tablero en la nube tendra los
echo  datos nuevos:  https://dashboard-bi-piura.streamlit.app/
echo ============================================================
echo.
pause
