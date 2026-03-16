@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [%date% %time%] 산지 공매 데이터 수집 시작...
python fetch_onbid.py
echo [%date% %time%] 완료
