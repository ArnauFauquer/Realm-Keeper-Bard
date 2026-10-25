<#
  Instala el entorno de generación imagen -> 3D de RealmKeeper Bard.

  - venv\                  Python 3.12 + trimesh/pymeshlab/moderngl (post-proceso)
  - trellis\src\           trellis.cpp compilado desde main con CUDA (Pixal3D y
                           --steps no están en la release v0.6.0)
  - trellis\runtime_main\  trellis-cli.exe + DLLs de ggml y CUDA
  - trellis\models\        pesos GGUF de TRELLIS.2 (Q8) y Pixal3D

  Requisitos que instala con winget si faltan: CUDA Toolkit 13.2 y Visual
  Studio 2022 Build Tools (C++). Ambos piden permisos de administrador.

  Uso:  powershell -ExecutionPolicy Bypass -File models_3d\setup_3d.ps1
#>
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$TrellisQuant = "q8"   # "q8" (~9.5 GB) o "q4" (~6 GB)
$CudaVersion = "13.2"  # compatible con el driver instalado (nvidia-smi: CUDA 13.2)
$CudaArch = "86"       # RTX 3080; ver https://developer.nvidia.com/cuda-gpus

function Log($m) { Write-Host "==> $m" -ForegroundColor Green }

# ---- entorno Python de post-proceso -----------------------------------------
if (-not (Test-Path "venv\Scripts\python.exe")) {
  Log "Creando venv (Python 3.12)"
  py -3.12 -m venv venv
}
$Py = Join-Path $Root "venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Py -m pip install -r requirements-3d.txt cmake ninja
# MoGe-2 (FOV de la cámara, como el Space de Pixal3D): PyTorch en CPU basta
& $Py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
& $Py -m pip install "git+https://github.com/microsoft/MoGe.git"

# ---- toolchain -----------------------------------------------------------------
$CudaPath = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v$CudaVersion"
if (-not (Test-Path "$CudaPath\bin\nvcc.exe")) {
  Log "Instalando CUDA Toolkit $CudaVersion"
  winget install --id Nvidia.CUDA --version $CudaVersion --silent --accept-package-agreements --accept-source-agreements
}
$VcVars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $VcVars)) {
  Log "Instalando Visual Studio 2022 Build Tools (C++)"
  winget install --id Microsoft.VisualStudio.2022.BuildTools --silent --accept-package-agreements --accept-source-agreements `
    --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621 --includeRecommended"
}

# ---- trellis.cpp -------------------------------------------------------------
if (-not (Test-Path "trellis\src")) {
  Log "Clonando trellis.cpp"
  git clone --recursive https://github.com/pwilkin/trellis.cpp.git trellis\src
  # post-replay: escribir la malla con --no-bake y leer la cabecera del volcado
  # en orden explícito (con MSVC salía desordenada)
  git -C trellis\src apply "$Root\patches\post_replay.patch"
}
$Runtime = "trellis\runtime_main"
if (-not (Test-Path "$Runtime\trellis-cli.exe")) {
  Log "Compilando trellis.cpp (CUDA sm_$CudaArch)"
  $Bat = Join-Path $env:TEMP "build_trellis.bat"
  @"
@echo off
call "$VcVars" >nul
set "PATH=$Root\venv\Scripts;$CudaPath\bin;%PATH%"
set "CUDA_PATH=$CudaPath"
cd /d "$Root\trellis\src"
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=$CudaArch -DGGML_OPENMP=OFF || exit /b 1
cmake --build build --target trellis-server trellis-cli post-replay || exit /b 1
"@ | Set-Content -Encoding ascii $Bat
  cmd /c $Bat
  if ($LASTEXITCODE -ne 0) { throw "falló la compilación de trellis.cpp" }
  New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
  Copy-Item "trellis\src\build\*.dll", "trellis\src\build\trellis-cli.exe", "trellis\src\build\trellis-server.exe", "trellis\src\build\post-replay.exe" $Runtime
  foreach ($dll in @("cudart64_*.dll", "cublas64_*.dll", "cublasLt64_*.dll")) {
    Get-ChildItem -Path $CudaPath -Recurse -Filter $dll | Select-Object -First 1 | Copy-Item -Destination $Runtime
  }
}

# ---- pesos -------------------------------------------------------------------
$ModelsDir = "trellis\models"
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
# compartidos (TRELLIS.2): decoders, DINOv3, BiRefNet + flows de TRELLIS.2
foreach ($m in @("birefnet", "dinov3", "ss_flow", "ss_dec", "shape_flow_512", "shape_flow_1024",
                 "shape_dec", "tex_flow_512", "tex_flow_1024", "tex_dec")) {
  $dest = Join-Path $ModelsDir "$m.gguf"
  if (-not (Test-Path $dest)) {
    Log "Descargando pesos TRELLIS.2: $m ($TrellisQuant)"
    Start-BitsTransfer -Source "https://huggingface.co/ilintar/trellis2-gguf/resolve/main/$TrellisQuant/$m.gguf" -Destination $dest
  }
}
# Pixal3D (fine-tune de TRELLIS.2 alineado a píxel): solo 5 ficheros propios
foreach ($m in @("naf", "ss_flow", "shape_flow_512", "shape_flow_1024", "tex_flow_1024")) {
  $dest = Join-Path $ModelsDir "pixal3d_$m.gguf"
  if (-not (Test-Path $dest)) {
    Log "Descargando pesos Pixal3D: $m"
    Start-BitsTransfer -Source "https://huggingface.co/vegax87/Pixal3D/resolve/main/pixal3d_$m.gguf" -Destination $dest
  }
}
Log "Listo."
