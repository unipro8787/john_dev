@echo off
title 테니스 예약 대기 서버
cd /d "%~dp0"
python -u remote_launcher.py
echo.
echo [서버 종료됨 - 오류가 있었다면 위 내용을 확인하세요]
pause
