
@echo off
title Minhas Financas

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: Ambiente Python nao encontrado.
    pause
    exit /b 1
)

echo Iniciando Minhas Financas...

".venv\Scripts\python.exe" -m streamlit run app.py

pause