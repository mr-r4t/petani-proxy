@echo off
title Petani Proxy - Captcha Solver Sidecar (:8877)
cd /d "%~dp0"
echo ========================================================
echo   PETANI PROXY - CAPTCHA SOLVER SIDECAR (:8877)
echo   Local AI Captcha Solver (Turnstile, hCaptcha, etc)
echo ========================================================
echo.
echo [*] Memulai server solver di http://127.0.0.1:8877...
.\.venv\Scripts\python.exe .\captcha-solver\server.py
pause
