@echo off
title Backend Server [Port 8000]
cd /d %~dp0
D:\Miniconda\envs\SpaceX\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
