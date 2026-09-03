# Publica el tablero en https://piura.suarbee.com (tu dominio en Cloudflare).
# El link es FIJO: no cambia entre corridas (es un tunel con nombre).
# Deja esta ventana ABIERTA mientras quieras que el link viva; Ctrl+C lo baja.
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

# 2) Publica por el tunel con nombre de Cloudflare.
Write-Host ""
Write-Host "Publicando en:  https://piura.suarbee.com" -ForegroundColor Cyan
Write-Host "Deja esta ventana abierta mientras quieras que el link viva (Ctrl+C para bajarlo)." -ForegroundColor Yellow
Write-Host ""
cloudflared tunnel run piura-dashboard
