<#
SHIBA AI MUSIC STUDIO - Auditoria do computador (SOMENTE LEITURA)

Este script NAO instala, NAO apaga e NAO modifica nada no sistema.
Ele apenas le informacoes e grava UM arquivo de relatorio (.md) na pasta
audit\output\ ao lado deste script.

Como executar (PowerShell, sem precisar de administrador):
    powershell -ExecutionPolicy Bypass -File .\audit\audit-pc.ps1

Opcional: incluir outras pastas/discos na busca por projetos musicais:
    powershell -ExecutionPolicy Bypass -File .\audit\audit-pc.ps1 -ExtraPaths "D:\Musicas","E:\Suno"
#>
param(
    [string[]]$ExtraPaths = @(),
    [int]$SearchDepth = 5
)

$ErrorActionPreference = 'SilentlyContinue'
$outDir = Join-Path $PSScriptRoot 'output'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$report = Join-Path $outDir "auditoria_$stamp.md"
$lines = New-Object System.Collections.Generic.List[string]

function Add([string]$text = '') { $lines.Add($text) }
function Section([string]$title) { Add ''; Add "## $title"; Add '' }
function Block([string]$cmdOutput) { Add '```'; Add ($cmdOutput.TrimEnd()); Add '```' }
function Run([string]$exe, [string[]]$argList) {
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { return "($exe nao encontrado no PATH)" }
    try { return (& $exe @argList 2>&1 | Out-String) } catch { return "(erro ao executar $exe)" }
}
function SizeGB($bytes) { '{0:N1} GB' -f ($bytes / 1GB) }
function FolderSize($path) {
    (Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
}

Write-Host 'Auditoria em andamento (somente leitura)...'

Add '# SHIBA AI MUSIC STUDIO - Relatorio de auditoria'
Add ''
Add "Gerado em: $(Get-Date -Format 'yyyy-MM-dd HH:mm')  |  Maquina: $env:COMPUTERNAME"

# ---------------------------------------------------------------- Sistema
Section '1. Sistema'
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
Add "- Windows: $($os.Caption) build $($os.BuildNumber)"
Add "- CPU: $($cpu.Name) ($($cpu.NumberOfCores) nucleos / $($cpu.NumberOfLogicalProcessors) threads)"
Add "- RAM: $(SizeGB $ram)"
$lp = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled
Add "- Long paths habilitado: $(if ($lp.LongPathsEnabled -eq 1) {'sim'} else {'NAO (pode quebrar instalacoes Python/ComfyUI)'})"

# ---------------------------------------------------------------- GPU / CUDA
Section '2. GPU, driver e CUDA'
Get-CimInstance Win32_VideoController | ForEach-Object {
    Add "- $($_.Name) | driver $($_.DriverVersion) | data $($_.DriverDate)"
}
Add ''
Add '### nvidia-smi'
Block (Run 'nvidia-smi' @())
Add '### nvcc (CUDA Toolkit)'
Block (Run 'nvcc' @('--version'))
Add "- CUDA_PATH: $env:CUDA_PATH"
$cudaRoot = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA'
if (Test-Path $cudaRoot) {
    Add "- Toolkits instalados: $((Get-ChildItem $cudaRoot -Directory).Name -join ', ')"
} else { Add '- Nenhum CUDA Toolkit em Program Files (normal: PyTorch traz o proprio runtime CUDA)' }

# ---------------------------------------------------------------- Python
Section '3. Python'
Add '### Launcher py (todas as versoes)'
Block (Run 'py' @('-0p'))
Add '### python no PATH'
Block ((Run 'where.exe' @('python')) + (Run 'python' @('--version')))
Add '### pip no PATH'
Block (Run 'where.exe' @('pip'))
Add '### Conda / venv managers'
Block ((Run 'conda' @('--version')) + (Run 'uv' @('--version')) + (Run 'pipx' @('--version')))
Add '### Pacotes de IA/audio no Python padrao'
$probe = @'
import importlib, sys
print("python", sys.version.split()[0], sys.executable)
for m in ["torch","torchaudio","torchvision","xformers","transformers","diffusers","accelerate",
          "audiocraft","demucs","librosa","soundfile","pydub","pedalboard","matchering",
          "whisper","faster_whisper","TTS","onnxruntime","numpy","gradio"]:
    try:
        mod = importlib.import_module(m)
        print(f"{m:15} {getattr(mod,'__version__','?')}")
    except Exception:
        print(f"{m:15} -")
try:
    import torch
    print("torch.cuda build :", torch.version.cuda)
    print("cuda disponivel  :", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("gpu              :", torch.cuda.get_device_name(0))
        print("capability       :", torch.cuda.get_device_capability(0))
        print("arch list        :", torch.cuda.get_arch_list())
except Exception as e:
    print("torch check erro :", e)
'@
$probeFile = Join-Path $env:TEMP 'shiba_probe.py'
Set-Content -Path $probeFile -Value $probe -Encoding UTF8
Block (Run 'python' @($probeFile))
Remove-Item $probeFile -Force

# ---------------------------------------------------------------- Ferramentas
Section '4. FFmpeg, Git, Node e ferramentas'
Block ((Run 'ffmpeg' @('-hide_banner','-version')) -split "`n" | Select-Object -First 3 | Out-String)
Add "- ffmpeg em: $((Run 'where.exe' @('ffmpeg')).Trim())"
Add "- git: $((Run 'git' @('--version')).Trim())"
Add "- node: $((Run 'node' @('--version')).Trim())"
Add "- claude: $((Run 'claude' @('--version')).Trim())"
Add "- ollama: $((Run 'ollama' @('--version')).Trim())"
Add "- docker: $((Run 'docker' @('--version')).Trim())"
Add "- wsl: $(((Run 'wsl' @('--status')) -replace "`0",'').Trim())"

# ---------------------------------------------------------------- Programas musicais
Section '5. Programas musicais e de audio instalados'
$keywords = 'Ableton|FL Studio|Reaper|REAPER|Cubase|Studio One|Bitwig|Pro Tools|Reason|Cakewalk|LMMS|Audacity|' +
            'iZotope|Ozone|Neutron|RX |Waves|Native Instruments|Kontakt|Komplete|Serum|Vital|Arturia|Spitfire|' +
            'Spectrasonics|Omnisphere|FabFilter|Valhalla|Melodyne|Celemony|Antares|Auto-Tune|ASIO|Focusrite|' +
            'Behringer|PreSonus|Steinberg|Voicemeeter|VB-Audio|UVI|Splice|Output|Toontrack|EZdrummer|Superior|' +
            'Guitar Rig|Neural DSP|Amplitube|BIAS|Helix|Ultimate Vocal Remover|UVR|Ocenaudio|Tenacity|MuseScore|' +
            'Surge|Dexed|Plugin Alliance|Soundtoys|Eventide|Audiority|LANDR|Suno|Udio|ElevenLabs|SoundID|Sonarworks'
$uninstall = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
             'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
             'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
$apps = Get-ItemProperty $uninstall | Where-Object { $_.DisplayName } |
        Select-Object DisplayName, DisplayVersion, Publisher -Unique
$music = $apps | Where-Object { $_.DisplayName -match $keywords -or $_.Publisher -match $keywords } |
         Sort-Object DisplayName
if ($music) {
    Add '| Programa | Versao | Fabricante |'
    Add '|---|---|---|'
    $music | ForEach-Object { Add "| $($_.DisplayName) | $($_.DisplayVersion) | $($_.Publisher) |" }
} else { Add '- Nenhum programa musical conhecido encontrado no registro.' }

Add ''
Add '### Pastas de plugins (VST2/VST3/CLAP)'
$pluginDirs = 'C:\Program Files\Common Files\VST3', 'C:\Program Files\Common Files\CLAP',
              'C:\Program Files\VSTPlugins', 'C:\Program Files\Steinberg\VSTPlugins',
              'C:\Program Files (x86)\VSTPlugins', 'C:\Program Files\Common Files\Avid\Audio\Plug-Ins'
foreach ($d in $pluginDirs) {
    if (Test-Path $d) {
        $items = Get-ChildItem $d -Force | Select-Object -ExpandProperty Name
        Add "- **$d** ($($items.Count) itens): $(($items | Select-Object -First 40) -join ', ')"
    }
}

Add ''
Add '### Dispositivos de audio'
Get-CimInstance Win32_SoundDevice | ForEach-Object { Add "- $($_.Name) ($($_.Manufacturer))" }

# ---------------------------------------------------------------- Modelos de IA
Section '6. Modelos e ferramentas de IA existentes'
$h = $env:USERPROFILE
$modelPlaces = [ordered]@{
    'HuggingFace cache'      = "$h\.cache\huggingface"
    'Torch hub cache'        = "$h\.cache\torch"
    'Whisper cache'          = "$h\.cache\whisper"
    'Ollama models'          = "$h\.ollama\models"
    'LM Studio models'       = "$h\.lmstudio\models"
    'LM Studio (antigo)'     = "$h\.cache\lm-studio"
    'Coqui TTS'              = "$env:LOCALAPPDATA\tts"
    'UVR models'             = "$env:LOCALAPPDATA\Programs\Ultimate Vocal Remover\models"
    'Pinokio'                = "$h\pinokio"
}
foreach ($k in $modelPlaces.Keys) {
    $p = $modelPlaces[$k]
    if (Test-Path $p) { Add "- **$k**: $p - $(SizeGB (FolderSize $p))" }
}
if ($env:HF_HOME) { Add "- HF_HOME definido: $env:HF_HOME" }
Add ''
Add '### Repositorios/apps de IA encontrados (ComfyUI, audiocraft, etc.)'
$aiNames = 'ComfyUI*','stable-diffusion-webui*','audiocraft*','YuE*','ACE-Step*','DiffRhythm*',
           'stable-audio*','MusicGen*','demucs*','ultimatevocalremover*','RVC*','Applio*',
           'so-vits*','bark*','AudioLDM*','riffusion*','InspireMusic*','SongGeneration*','pinokio*'
$roots = @("$h\Desktop","$h\Documents","$h\Downloads","$h","C:\AI","C:\IA","C:\tools") + $ExtraPaths
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -ne 'C:\' -and $_.Used -gt 0 } |
    ForEach-Object { $roots += $_.Root }
$foundAI = foreach ($r in ($roots | Select-Object -Unique)) {
    if (Test-Path $r) { Get-ChildItem $r -Directory -Recurse -Depth 2 -Include $aiNames -Force }
}
$foundAI | Select-Object -Unique FullName | ForEach-Object { Add "- $($_.FullName)" }
Add ''
Add '### Arquivos de pesos soltos (> 100 MB: .safetensors .ckpt .pt .pth .bin .gguf .onnx)'
$weights = foreach ($r in ($roots | Select-Object -Unique)) {
    if (Test-Path $r) {
        Get-ChildItem $r -Recurse -File -Depth $SearchDepth -Force -Include *.safetensors,*.ckpt,*.pt,*.pth,*.gguf,*.onnx,*.bin |
            Where-Object { $_.Length -gt 100MB -and $_.FullName -notmatch '\\\.cache\\|\\\.ollama\\' }
    }
}
$weights | Sort-Object Length -Descending | Select-Object -First 60 |
    ForEach-Object { Add "- $($_.FullName) ($(SizeGB $_.Length))" }

# ---------------------------------------------------------------- Disco
Section '7. Espaco em disco'
Add '| Unidade | Rotulo | Tipo | Livre | Total |'
Add '|---|---|---|---|---|'
$phys = @{}
Get-PhysicalDisk | ForEach-Object { $phys[[string]$_.DeviceId] = "$($_.MediaType) $($_.BusType)" }
Get-Volume | Where-Object { $_.DriveLetter -and $_.Size -gt 0 } | Sort-Object DriveLetter | ForEach-Object {
    $num = (Get-Partition -DriveLetter $_.DriveLetter).DiskNumber
    Add "| $($_.DriveLetter): | $($_.FileSystemLabel) | $($phys[[string]$num]) | $(SizeGB $_.SizeRemaining) | $(SizeGB $_.Size) |"
}

# ---------------------------------------------------------------- Projetos musicais
Section '8. Projetos musicais locais em andamento'
$projExt = '*.als','*.flp','*.rpp','*.cpr','*.song','*.bwproject','*.ptx','*.logicx','*.reason',
           '*.cwp','*.mmp','*.mmpz','*.aup','*.aup3','*.mid','*.midi'
$projRoots = @("$h\Documents","$h\Music","$h\Desktop","$h\Downloads","$h\OneDrive") + $ExtraPaths
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -ne 'C:\' -and $_.Used -gt 0 } |
    ForEach-Object { $projRoots += $_.Root }
$projects = foreach ($r in ($projRoots | Select-Object -Unique)) {
    if (Test-Path $r) { Get-ChildItem $r -Recurse -File -Depth $SearchDepth -Force -Include $projExt }
}
$projects = $projects | Sort-Object LastWriteTime -Descending
Add "Total de arquivos de projeto/MIDI: $(@($projects).Count)"
Add ''
$projects | Select-Object -First 50 | ForEach-Object {
    Add "- $($_.LastWriteTime.ToString('yyyy-MM-dd')) | $($_.FullName)"
}
Add ''
Add '### Audio (possiveis faixas do Suno, stems, masters)'
$audio = foreach ($r in ($projRoots | Select-Object -Unique)) {
    if (Test-Path $r) {
        Get-ChildItem $r -Recurse -File -Depth $SearchDepth -Force -Include *.wav,*.mp3,*.flac,*.aiff,*.aif,*.m4a,*.ogg
    }
}
$audio = @($audio)
Add "Total de arquivos de audio: $($audio.Count) ($(SizeGB (($audio | Measure-Object Length -Sum).Sum)))"
Add ''
Add 'Pastas com mais arquivos de audio:'
$audio | Group-Object DirectoryName | Sort-Object Count -Descending | Select-Object -First 25 |
    ForEach-Object { Add "- $($_.Count) arquivos | $($_.Name)" }
$suno = $audio | Where-Object { $_.FullName -match 'suno' }
if ($suno) { Add ''; Add "Arquivos com 'suno' no caminho: $($suno.Count)" }

# ---------------------------------------------------------------- Conflitos
Section '9. Sinais de possiveis conflitos (checagem automatica)'
$pyList = (Run 'py' @('-0p'))
$pyCount = ([regex]::Matches($pyList, 'python\.exe', 'IgnoreCase')).Count
if ($pyCount -gt 1) { Add "- [!] $pyCount instalacoes de Python detectadas - usar venv por projeto e o launcher 'py -3.x'." }
if ((Run 'where.exe' @('python')) -match 'WindowsApps') { Add '- [!] Alias da Microsoft Store para python no PATH (WindowsApps) - pode interceptar o comando python.' }
$ffCount = ((Run 'where.exe' @('ffmpeg')) -split "`n" | Where-Object { $_ -match 'ffmpeg' }).Count
if ($ffCount -gt 1) { Add "- [!] $ffCount ffmpeg no PATH - versoes diferentes podem ser usadas por ferramentas diferentes." }
if ($env:PYTHONPATH) { Add "- [!] PYTHONPATH global definido ($env:PYTHONPATH) - pode misturar pacotes entre ambientes." }
if (-not (Get-Command 'git' -ErrorAction SilentlyContinue)) { Add '- [!] Git nao encontrado - necessario para ComfyUI e repositorios de IA.' }
Add '- Lembrete: RTX 5060 Ti e arquitetura Blackwell (sm_120). Exige PyTorch com CUDA 12.8+ (wheels cu128 ou mais novas). Torch antigo (cu118/cu121/cu124) gera "no kernel image is available".'

Set-Content -Path $report -Value $lines -Encoding UTF8
Write-Host ''
Write-Host "Relatorio gerado: $report"
