@echo off
cd /d "%~dp0"
python -m retroport.workbench.app
if errorlevel 1 pause
