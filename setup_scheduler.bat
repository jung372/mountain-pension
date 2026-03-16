@echo off
chcp 65001 > nul
echo ======================================
echo  온비드 산지 공매 데이터 수집
echo  Windows 작업 스케줄러 등록 스크립트
echo ======================================
echo.

set "SCRIPT_DIR=%~dp0"
set "BATCH_FILE=%SCRIPT_DIR%run_fetch.bat"
set "TASK_NAME=OnbidForestFetch"

echo [1] 기존 작업 삭제 중 (있을 경우)...
schtasks /delete /tn "%TASK_NAME%" /f > nul 2>&1

echo [2] 매일 오전 7시 자동 실행 작업 등록 중...
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%BATCH_FILE%\"" ^
  /sc daily ^
  /st 07:00 ^
  /ru "%USERNAME%" ^
  /rl highest ^
  /f

if %errorlevel% == 0 (
    echo.
    echo [완료] 작업 스케줄러 등록 성공!
    echo  - 작업 이름 : %TASK_NAME%
    echo  - 실행 파일 : %BATCH_FILE%
    echo  - 실행 시간 : 매일 오전 07:00
    echo.
    echo [확인] 지금 즉시 한번 실행하시겠습니까? (Y/N)
    set /p RUN_NOW="> "
    if /i "%RUN_NOW%"=="Y" (
        echo.
        echo 지금 실행 중...
        call "%BATCH_FILE%"
    )
) else (
    echo.
    echo [오류] 작업 스케줄러 등록 실패.
    echo  - 관리자 권한으로 실행하세요.
    echo  - 우클릭 → "관리자 권한으로 실행"
)

echo.
pause
