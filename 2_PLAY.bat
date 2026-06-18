@echo off
chcp 65001 >nul
title AI 게임 - 시작
cd /d "%~dp0"
REM 한글 로그 인코딩 크래시 방지
set PYTHONUTF8=1
echo 게임을 시작합니다. 메뉴에서 솔로(AI 대결/웨이브) 또는 멀티를 고르세요.
echo  - 멀티: '멀티플레이' 선택 -^> 이름 입력 -^> 친구와 둘 다 '준비완료' 누르면 시작!
echo  - 같은 시간에 같이 켜야 서로 매칭됩니다.
python play_online.py
if errorlevel 1 (
    echo.
    echo [!] 게임이 종료되었거나 오류가 났습니다.
    echo     같은 폴더의 crash_log.txt 가 있으면 승원이에게 보내주세요.
    pause
)
