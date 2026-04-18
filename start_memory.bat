@echo off
title Memory Server [Port 8001]
cd /d %~dp0
set PYTHON=D:\Miniconda\envs\SpaceX\python.exe
"%PYTHON%" -m Memory.server
pause
