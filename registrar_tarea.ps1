# Registra la Tarea Programada de Windows que actualiza los datos de Piura
# Y LOS SUBE A LA NUBE. Corre diario a las 07:00 y tambien al iniciar sesion;
# se pone al dia si el equipo estuvo apagado a esa hora (StartWhenAvailable).
# Asi, cada vez que la PC este encendida un rato, el tablero en la nube se
# actualiza solo. (SNIRH bloquea la nube: la descarga tiene que salir de Peru.)
#
# Como usarlo: correlo desde una terminal NORMAL; el script se auto-eleva y
# Windows te pedira confirmacion (UAC). Solo dale "Si".
#   powershell -ExecutionPolicy Bypass -File "D:\DASHBOAR BI\registrar_tarea.ps1"

# --- Auto-elevacion: crear la tarea requiere permisos de administrador ---
$id      = [Security.Principal.WindowsIdentity]::GetCurrent()
$esAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
             [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Write-Host "Pidiendo permisos de administrador (acepta el aviso de Windows)..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
    exit
}

$raiz    = "D:\DASHBOAR BI"
$wrapper = "D:\DASHBOAR BI\actualizar_y_publicar.bat"
$nombre  = "DashboardBI Piura - Actualizar datos"

$accion = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$wrapper`"" -WorkingDirectory $raiz
$t1 = New-ScheduledTaskTrigger -Daily -At 7:00am
$t2 = New-ScheduledTaskTrigger -AtLogOn
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$pr  = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $t1, $t2 `
      -Settings $set -Principal $pr -Force -ErrorAction Stop `
      -Description "Actualiza caudales (SNIRH) y clima (NASA POWER) de Piura y los sube a GitHub; Streamlit Cloud se redepliega solo."
    Write-Host ""
    Write-Host "OK: tarea registrada '$nombre'." -ForegroundColor Green
    Write-Host "Para probarla ahora mismo:  Start-ScheduledTask -TaskName '$nombre'"
} catch {
    Write-Host ""
    Write-Host "ERROR: no se pudo registrar la tarea." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}
