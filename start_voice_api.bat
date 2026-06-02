@echo off
title Echoo Voice API Server (GPT-SoVITS)
echo Starting GPT-SoVITS API Server in Background Mode...
cd /d "C:\Users\Neha Mokshith\Downloads\GPT-SoVITS-v3lora-20250228\GPT-SoVITS-v3lora-20250228"
.\runtime\python.exe api_v2.py -a 127.0.0.1 -p 9880
pause
