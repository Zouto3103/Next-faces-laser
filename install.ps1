<#
.SYNOPSIS
    Instala (copia) o add-in FusionLaserNest na pasta AddIns do Fusion no Windows.

.DESCRIPTION
    Copia a pasta FusionLaserNest\ deste repositorio para
    %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionLaserNest
    (local documentado pela Autodesk para add-ins Python instalados manualmente).

    Rode este script sempre que quiser atualizar uma instalacao ja existente;
    ele apaga a pasta de destino antes de copiar para evitar arquivos antigos
    (como um log.txt de uma versao anterior) ficarem misturados com os novos.

.EXAMPLE
    .\install.ps1
#>

$ErrorActionPreference = "Stop"

$sourceDir = Join-Path $PSScriptRoot "FusionLaserNest"
$addInsRoot = Join-Path $env:APPDATA "Autodesk\Autodesk Fusion 360\API\AddIns"
$destDir = Join-Path $addInsRoot "FusionLaserNest"

if (-not (Test-Path $sourceDir)) {
    Write-Error "Pasta de origem nao encontrada: $sourceDir"
}

if (-not (Test-Path $addInsRoot)) {
    New-Item -ItemType Directory -Force -Path $addInsRoot | Out-Null
}

if (Test-Path $destDir) {
    Write-Host "Removendo instalacao anterior em: $destDir"
    Remove-Item -Recurse -Force $destDir
}

Write-Host "Copiando $sourceDir -> $destDir"
Copy-Item -Recurse -Force $sourceDir $destDir

# Nao copiar a pasta de testes nem arquivos de cache Python para dentro do Fusion.
$testsDir = Join-Path $destDir "tests"
if (Test-Path $testsDir) {
    Remove-Item -Recurse -Force $testsDir
}
Get-ChildItem -Path $destDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Instalado em: $destDir"
Write-Host "Abra o Fusion, va em UTILITIES > Add-Ins (Scripts and Add-Ins), aba 'Add-Ins',"
Write-Host "selecione 'FusionLaserNest' e clique em Run (marque 'Run on Startup' se quiser)."
