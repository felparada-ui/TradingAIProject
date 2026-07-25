<#
.SYNOPSIS
    PRO TRADER — Scheduler Automatico para Windows (PowerShell)
.DESCRIPTION
    Conecta MT5, ejecuta pipeline multi-estrategia cada hora en sesion USA.
    Lun-Vie 9:30-16:00 ET. Con logging y notificaciones.
.NOTES
    Ejecutar: powershell -ExecutionPolicy Bypass -File run_trader_scheduler.ps1
#>

$Capital = 1024.67
$LogFile = "logs\trader_scheduler.log"
$ScriptDir = "src\pro_trader_crew"
$IntervalMinutes = 60

# Asegurar directorio de logs
$null = New-Item -ItemType Directory -Force -Path "logs"

function Write-Log($Message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $LogFile -Append -Encoding UTF8
    Write-Host "$timestamp - $Message"
}

function Test-MarketHours {
    $now = Get-Date
    $dayOfWeek = $now.DayOfWeek.value__
    $totalMinutes = $now.Hour * 60 + $now.Minute
    
    # Lun-Vie (1-5), 9:30-16:00 ET
    return ($dayOfWeek -ge 1 -and $dayOfWeek -le 5 -and $totalMinutes -ge 570 -and $totalMinutes -le 960)
}

function Test-MT5Connection {
    Write-Log "Verificando conexion MT5..."
    $result = python scripts/test_mt5_connection.py 2>&1
    $output = $result -join "`n"
    if ($output -match "CONEXION EXITOSA") {
        Write-Log "✅ MT5 conectado correctamente"
        return $true
    }
    Write-Log "⚠️ MT5 no disponible, usando Binance paper"
    return $false
}

function Run-Pipeline {
    Write-Log "Ejecutando pipeline multi-estrategia..."
    
    $result = python src/pro_trader_crew/main.py 2>&1
    $output = $result -join "`n"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Log "✅ Pipeline completado exitosamente"
        # Extraer resumen
        if ($output -match "Trades hoy: (\d+).*PnL: \$([\d\.\-]+)") {
            Write-Log "📊 Trades: $($Matches[1]) | PnL: `$$($Matches[2])"
        }
        return $true
    }
    
    Write-Log "⚠️ Pipeline finalizado con codigo: $LASTEXITCODE"
    return $false
}

function Show-Menu {
    Clear-Host
    Write-Host @"
============================================================
  PRO TRADER — Scheduler Automatico (PowerShell)
============================================================

  1. Iniciar scheduler (cada hora, Lun-Vie)
  2. Ejecutar un solo ciclo
  3. Probar conexion MT5
  4. Ver ultimos logs
  5. Salir

"@
    $opcion = Read-Host "Selecciona (1-5)"
    return $opcion
}

function Start-Scheduler {
    Clear-Host
    Write-Log "========================================"
    Write-Log "🚀 SCHEDULER INICIADO"
    Write-Log "   Capital: `$$Capital"
    Write-Log "   Horario: Lun-Vie 9:30-16:00 ET"
    Write-Log "   Intervalo: $IntervalMinutes minutos"
    Write-Log "========================================"
    
    # Probar MT5 al inicio
    Test-MT5Connection
    
    while ($true) {
        if (Test-MarketHours) {
            Write-Log "📡 Horario valido - Ejecutando pipeline..."
            Run-Pipeline
        } else {
            Clear-Host
            Write-Host @"
============================================================
  ⏳ Fuera de horario de mercado
  Horario: Lun-Vie 9:30-16:00 ET
  Proximo ciclo en hora valida
  Presiona CTRL+C para detener
============================================================
"@
            Write-Log "⏳ Fuera de horario"
        }
        
        Write-Log "⏳ Proximo ciclo en $IntervalMinutes minutos..."
        
        # Esperar en intervalos de 10s para poder detectar CTRL+C
        for ($i = 0; $i -lt $IntervalMinutes * 6; $i++) {
            Start-Sleep -Seconds 10
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -eq 'C' -and $key.Modifiers -eq 'Control') {
                    Write-Log "🛑 Scheduler detenido por usuario"
                    return
                }
            }
        }
    }
}

# ── MAIN ──
Write-Log "========================================"
Write-Log "🏦 PRO TRADER SCHEDULER INICIADO"
Write-Log "========================================"

while ($true) {
    $opcion = Show-Menu
    
    switch ($opcion) {
        "1" { Start-Scheduler }
        "2" { 
            Clear-Host
            Run-Pipeline
            Write-Host "`nPresiona Enter para volver..." -NoNewline
            $null = Read-Host
        }
        "3" {
            Clear-Host
            Test-MT5Connection
            Write-Host "`nPresiona Enter para volver..." -NoNewline
            $null = Read-Host
        }
        "4" {
            Clear-Host
            Write-Host "=== ULTIMOS LOGS ==="
            if (Test-Path $LogFile) {
                Get-Content $LogFile -Tail 30
            } else {
                Write-Host "Sin logs aun"
            }
            Write-Host "`nPresiona Enter para volver..." -NoNewline
            $null = Read-Host
        }
        "5" { 
            Write-Log "🛑 Programa cerrado por usuario"
            exit 
        }
    }
}
