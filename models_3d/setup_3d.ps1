<#
  Sets up the image -> 3D generation environment of RealmKeeper Bard.

  - venv\                  Python 3.12 + trimesh/pymeshlab/moderngl (post-processing)
  - trellis\src\           trellis.cpp built from main with CUDA (Pixal3D and
                           --steps are not in the v0.6.0 release)
  - trellis\runtime_main\  trellis-cli.exe + ggml and CUDA DLLs
  - trellis\models\        Pixal3D GGUF weights + the decoders shared with TRELLIS.2 (Q8)

  Requirements installed with winget if missing: CUDA Toolkit 13.2 and Visual
  Studio 2022 Build Tools (C++). Both require administrator permissions.

  Usage:  powershell -ExecutionPolicy Bypass -File models_3d\setup_3d.ps1
#>
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$TrellisQuant = "q8"   # shared decoders: "q8" or "q4"
$CudaVersion = "13.2"  # compatible with the installed driver (nvidia-smi: CUDA 13.2)
$CudaArch = "86"       # RTX 3080; see https://developer.nvidia.com/cuda-gpus

function Log($m) { Write-Host "==> $m" -ForegroundColor Green }

# ---- post-processing Python environment -----------------------------------------
if (-not (Test-Path "venv\Scripts\python.exe")) {
  Log "Creating venv (Python 3.12)"
  py -3.12 -m venv venv
}
$Py = Join-Path $Root "venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Py -m pip install -r requirements-3d.txt cmake ninja
# MoGe-2 (camera FOV, like the Pixal3D Space): PyTorch on CPU is enough
& $Py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
& $Py -m pip install "git+https://github.com/microsoft/MoGe.git"

# ---- toolchain -----------------------------------------------------------------
$CudaPath = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v$CudaVersion"
if (-not (Test-Path "$CudaPath\bin\nvcc.exe")) {
  Log "Installing CUDA Toolkit $CudaVersion"
  winget install --id Nvidia.CUDA --version $CudaVersion --silent --accept-package-agreements --accept-source-agreements
}
$VcVars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $VcVars)) {
  Log "Installing Visual Studio 2022 Build Tools (C++)"
  winget install --id Microsoft.VisualStudio.2022.BuildTools --silent --accept-package-agreements --accept-source-agreements `
    --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621 --includeRecommended"
}

# ---- trellis.cpp -------------------------------------------------------------
if (-not (Test-Path "trellis\src")) {
  Log "Cloning trellis.cpp"
  git clone --recursive https://github.com/pwilkin/trellis.cpp.git trellis\src
  # post-replay: write the mesh with --no-bake and read the dump header
  # in explicit order (it came out scrambled with MSVC)
  git -C trellis\src apply "$Root\patches\post_replay.patch"
}
$Runtime = "trellis\runtime_main"
if (-not (Test-Path "$Runtime\trellis-cli.exe")) {
  Log "Building trellis.cpp (CUDA sm_$CudaArch)"
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
  if ($LASTEXITCODE -ne 0) { throw "trellis.cpp build failed" }
  New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
  Copy-Item "trellis\src\build\*.dll", "trellis\src\build\trellis-cli.exe", "trellis\src\build\trellis-server.exe", "trellis\src\build\post-replay.exe" $Runtime
  foreach ($dll in @("cudart64_*.dll", "cublas64_*.dll", "cublasLt64_*.dll")) {
    Get-ChildItem -Path $CudaPath -Recurse -Filter $dll | Select-Object -First 1 | Copy-Item -Destination $Runtime
  }
}

# ---- weights -------------------------------------------------------------------
$ModelsDir = "trellis\models"
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
# shared with TRELLIS.2 (Pixal3D does not change them): decoders, DINOv3 and BiRefNet
foreach ($m in @("birefnet", "dinov3", "ss_dec", "shape_dec", "tex_dec")) {
  $dest = Join-Path $ModelsDir "$m.gguf"
  if (-not (Test-Path $dest)) {
    Log "Downloading shared weights: $m ($TrellisQuant)"
    Start-BitsTransfer -Source "https://huggingface.co/ilintar/trellis2-gguf/resolve/main/$TrellisQuant/$m.gguf" -Destination $dest
  }
}
# Pixal3D (pixel-aligned fine-tune of TRELLIS.2): only 5 files of its own
foreach ($m in @("naf", "ss_flow", "shape_flow_512", "shape_flow_1024", "tex_flow_1024")) {
  $dest = Join-Path $ModelsDir "pixal3d_$m.gguf"
  if (-not (Test-Path $dest)) {
    Log "Downloading Pixal3D weights: $m"
    Start-BitsTransfer -Source "https://huggingface.co/vegax87/Pixal3D/resolve/main/pixal3d_$m.gguf" -Destination $dest
  }
}
Log "Done."
