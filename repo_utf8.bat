@echo off
REM UTF-8環境設定でrepo.batを実行するラッパー
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call repo.bat %*