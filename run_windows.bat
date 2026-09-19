@echo off
setlocal
cd /d "%~dp0"
title NashvilleHealth Local Prototype
where python >nul 2>nul || (echo Python was not found. Install Python 3.12 first.& pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
python check_setup.py
streamlit run app.py
