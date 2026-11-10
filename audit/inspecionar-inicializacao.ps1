<#
SHIBA OS - Como Hermes, Ollama e Telegram sao iniciados hoje (SOMENTE LEITURA)

NAO inicia, para, instala ou altera nada. Apenas le processos, servicos,
tarefas agendadas, itens de inicializacao e o conteudo do shiba.cmd, e grava
UM relatorio em audit\output\. Tokens e chaves encontrados sao mascarados.

Como executar:
    powershell -ExecutionPolicy Bypass -File .\audit\inspecionar-inicializacao.ps1
    (opcional) -HermesDir "C:\SHIBA-OS HERMES"
#>
param([string]$HermesDir = 'C:\SHIBA-OS HERMES')

$ErrorActionPreference = 'SilentlyContinue'
$outDir = Join-Path $PSScriptRoot 'output'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$report = Join-Path $outDir "inicializacao_$(Get-Date -Format 'yyyy-MM-dd_HHmm').md"
$lines = New-Object System.Collections.Generic.List[string]
$pattern = 'hermes|ollama|telegram|shiba|gateway'

function Add([string]$text = '') { $lines.Add($text) }
function Section([string]$title) { Add ''; Add "## $title"; Add '' }
function Mask([string]$text) {
    $text = $text -replace '\d{8,10}:[A-Za-z0-9_-]{30,}', '<TOKEN_TELEGRAM_MASCARADO>'
    $text = $text -replace '(sk-[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+', '$1<MASCARADO>'
    $text -replace '(?i)((token|key|secret|senha|password)\s*[=:]\s*)\S+', '$1<MASCARADO>'
}
function Block([string]$text) { Add '```'; Add (Mask $text).TrimEnd(); Add '```' }

Write-Host 'Inspecionando inicializacao (somente leitura)...'
Add '# SHIBA OS - Inspecao da inicializacao'
Add ''
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
Add "Gerado em: $(Get-Date -Format 'yyyy-MM-dd HH:mm') | Ultimo boot: $boot"

Section '1. Processos relacionados rodando agora'
$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match 'ollama|wsl|python|node|uv' -or $_.CommandLine -match $pattern
}
if ($procs) {
    Add '| PID | Processo | Inicio | Linha de comando |'
    Add '|---|---|---|---|'
    foreach ($p in $procs) {
        $cmd = (Mask "$($p.CommandLine)") -replace '\|', '/'
        Add "| $($p.ProcessId) | $($p.Name) | $($p.CreationDate) | $cmd |"
    }
} else { Add '- Nenhum processo relacionado encontrado.' }
$pyHermes = @($procs | Where-Object { $_.CommandLine -match 'hermes' })
if ($pyHermes.Count -gt 1) { Add ''; Add "- [!] $($pyHermes.Count) processos com 'hermes' na linha de comando: possivel duplicidade." }

Section '2. Portas em escuta (Ollama usa 11434)'
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 11434, 8000, 8080, 8642, 3000 } | ForEach-Object {
    $owner = (Get-Process -Id $_.OwningProcess).ProcessName
    Add "- porta $($_.LocalPort) em $($_.LocalAddress) -> $owner (PID $($_.OwningProcess))"
}

Section '3. Servicos do Windows'
Get-CimInstance Win32_Service | Where-Object { $_.Name -match $pattern -or $_.PathName -match $pattern } | ForEach-Object {
    Add "- $($_.Name) | estado $($_.State) | inicio $($_.StartMode) | $(Mask $_.PathName)"
}

Section '4. Tarefas agendadas'
Get-ScheduledTask | ForEach-Object {
    $t = $_
    $acts = ($t.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' ; '
    if ($t.TaskName -match $pattern -or $acts -match $pattern) {
        $trig = ($t.Triggers | ForEach-Object { $_.CimClass.CimClassName -replace 'MSFT_Task', '' }) -join ', '
        Add "- **$($t.TaskPath)$($t.TaskName)** | estado $($t.State) | gatilhos: $trig"
        Add "  - acao: $(Mask $acts)"
        Add "  - multiplas instancias: $($t.Settings.MultipleInstances)"
    }
}

Section '5. Inicializacao automatica (pastas Startup e registro Run)'
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in [Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup')) {
    Get-ChildItem $dir -File | ForEach-Object {
        $target = if ($_.Extension -eq '.lnk') { $l = $shell.CreateShortcut($_.FullName); "$($l.TargetPath) $($l.Arguments)" } else { '' }
        Add "- [$dir] $($_.Name) -> $(Mask $target)"
    }
}
foreach ($key in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run') {
    $props = Get-ItemProperty $key
    if ($props) {
        $props.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | ForEach-Object {
            Add "- [$key] $($_.Name) -> $(Mask "$($_.Value)")"
        }
    }
}

Section '6. Ollama'
Add "- executavel: $((Get-Command ollama).Source)"
Block ((& ollama list 2>&1 | Out-String))
Add "- OLLAMA_HOST: $env:OLLAMA_HOST | OLLAMA_MODELS: $env:OLLAMA_MODELS"

Section '7. WSL (o Hermes pode rodar dentro dele)'
Block (((& wsl.exe -l -v 2>&1 | Out-String) -replace "`0", ''))

Section "8. Conteudo do shiba.cmd e lancadores em $HermesDir"
if (Test-Path $HermesDir) {
    Get-ChildItem $HermesDir -File -Include *.cmd, *.bat -Recurse -Depth 1 | ForEach-Object {
        Add "### $($_.FullName)"
        Block (Get-Content $_.FullName -Raw)
    }
    Add '### Arquivos .log e .txt mais recentes (somente nomes)'
    Get-ChildItem $HermesDir -File -Recurse -Depth 3 -Include *.log, *.txt | Sort-Object LastWriteTime -Descending |
        Select-Object -First 15 | ForEach-Object { Add "- $($_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')) | $($_.FullName)" }
} else { Add "- Pasta $HermesDir nao encontrada." }
foreach ($d in "$env:USERPROFILE\.hermes", "$env:LOCALAPPDATA\hermes") {
    if (Test-Path $d) { Add "- Pasta de dados do Hermes encontrada: $d" }
}

Section '9. Energia e login'
$since = (Get-Date).AddDays(-30)
$falls = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 41; StartTime = $since })
Add "- Desligamentos inesperados (Kernel-Power 41) nos ultimos 30 dias: $($falls.Count)"
$falls | Select-Object -First 10 | ForEach-Object { Add "  - $($_.TimeCreated)" }
$auto = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon').AutoAdminLogon
Add "- Login automatico do Windows: $(if ($auto -eq '1') {'ligado'} else {'desligado'})"
Add '- Ligar sozinho apos queda de energia depende da BIOS ("Restore on AC Power Loss"), nao do Windows.'

Set-Content -Path $report -Value $lines -Encoding UTF8
Write-Host "Relatorio gerado: $report"
