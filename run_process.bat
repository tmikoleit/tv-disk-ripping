@echo off
REM Wrapper script to run disk ripping automation tool from Operational folder
REM Usage: run_process.bat community 1 2

cd /d "%~dp0Operational"
python process_rips.py %*
