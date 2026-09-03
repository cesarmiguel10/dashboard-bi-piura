# Comparte el tablero por un link publico de Cloudflare (demo).
# Deja esta ventana ABIERTA mientras tu amigo lo revisa; con Ctrl+C se cierra
# el link. Cada vez que lo corres, la direccion puede cambiar (tunel gratis).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File "D:\DASHBOAR BI\compartir.ps1"

$raiz = "D:\DASHBOAR BI"
$py   = "$raiz\.venv\Scripts\python.exe"
Set-Location $raiz

# 1) Levanta el tablero (Streamlit) si no esta corriendo en el 8501.
$enUso = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if (-not $enUso) {
    Write-Host "Iniciando el tablero (Streamlit)..." -ForegroundColor Cyan
    Start-Process -FilePath $py -ArgumentList "-m", "streamlit", "run", "app.py" -WorkingDirectory $raiz
    Start-Sleep -Seconds 6
} else {
    Write-Host "El tablero ya esta corriendo en el 8501." -ForegroundColor Green
}

# 2) Abre el tunel de Cloudflare y muestra el link (en el recuadro de abajo).
Write-Host ""
Write-Host "Abriendo el link de Cloudflare. Comparte la direccion trycloudflare.com que aparece abajo." -ForegroundColor Cyan
Write-Host "Deja esta ventana abierta mientras tu amigo lo revisa (Ctrl+C para cerrar)." -ForegroundColor Yellow
Write-Host ""
cloudflared tunnel --url http://localhost:8501 --no-autoupdate
