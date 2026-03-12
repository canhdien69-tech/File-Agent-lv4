@echo off
cd /d "D:\SunnyV5\File Agent V5"
echo Dang khoi dong Sunny AI v5.0...
python -m uvicorn sunny_web:app --host 0.0.0.0 --port 7860
pause
