@echo off
title Memory Server [Port 8001]
cd /d %~dp0
D:\Miniconda\envs\SpaceX\python.exe -m Memory.server
pause
