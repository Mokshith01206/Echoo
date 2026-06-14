@echo off
title Echoo AI Launcher
echo ============================================================
echo  Echoo AI - Starting Everything
echo ============================================================

echo [*] Cleaning up any old stuck API servers...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":9880" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8080" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [1/2] Skipping GPT-SoVITS Voice API (Running in Text Mode)...
:: start "GPT-SoVITS API" cmd /k "cd /d "C:\Users\Neha Mokshith\Downloads\GPT-SoVITS-v3lora-20250228\GPT-SoVITS-v3lora-20250228" && set is_half=True && set IS_HALF=True && .\runtime\python.exe api_v2.py -a 127.0.0.1 -p 9880"

echo [2/2] Starting Echoo Backend...
cd /d "C:\Users\Neha Mokshith\OneDrive\Documents\Echo"
.\.venv\Scripts\python.exe echo.py
