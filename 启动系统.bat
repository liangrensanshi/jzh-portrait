@echo off
cd /d "%~dp0"
echo 正在启动记账户画像系统...
echo 浏览器打开 http://localhost:8501
python -m streamlit run app.py
pause
