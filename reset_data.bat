@echo off
chcp 65001 >nul
echo Будут удалены лайки, история, сессия и ключи сервисов Loonify.
echo Папка: %USERPROFILE%\.loonify
choice /M "Продолжить"
if errorlevel 2 exit /b
rmdir /s /q "%USERPROFILE%\.loonify"
echo Готово, Loonify запустится с чистого листа.
pause
