$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend virtual environment was not found: $python"
}

Push-Location $PSScriptRoot
try {
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name course-agent-backend `
        --collect-all chromadb `
        --collect-all sentence_transformers `
        --collect-all transformers `
        --collect-all bcrypt `
        --collect-submodules passlib `
        --collect-submodules jose `
        --hidden-import sqlalchemy.dialects.mysql.pymysql `
        --collect-submodules langgraph `
        --collect-submodules langchain_deepseek `
        --collect-all alembic `
        --add-data "alembic;alembic" `
        --add-data "alembic.ini;." `
        desktop_backend.py
    if ($LASTEXITCODE -ne 0) {
        throw "Backend executable build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
