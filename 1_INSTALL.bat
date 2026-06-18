@echo off
chcp 65001 >nul
title AI 좀비 멀티 - 설치
echo ============================================
echo   AI 좀비 1:1 멀티 - 필요한 것 설치 (최초 1회)
echo ============================================
echo.

REM 파이썬 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] 파이썬이 설치되어 있지 않습니다.
    echo     https://www.python.org/downloads/ 에서 설치하세요.
    echo     설치 화면에서 "Add python.exe to PATH" 체크 필수!
    echo.
    pause
    exit /b 1
)

echo 파이썬 확인됨:
python --version
echo.
echo 게임 라이브러리(panda3d) 설치 중... (인터넷 필요, 1~3분)
echo.
python -m pip install --upgrade pip
python -m pip install panda3d==1.10.16 panda3d-gltf==1.3.0
echo.
if errorlevel 1 (
    echo [!] 설치 중 오류가 발생했습니다. 위 메시지를 승원이에게 보내주세요.
) else (
    echo [완료] 이제 2_PLAY.bat 로 게임을 시작하세요!
)
echo.
pause
