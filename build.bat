@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PY=C:\Users\nerpi\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PY%" set PY=python

echo [1/3] Установка библиотек...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install pywebview yt-dlp ytmusicapi yandex-music spotipy pyinstaller pillow || goto :err

echo [2/3] Сборка Loonify.exe...
"%PY%" -m PyInstaller --noconfirm --clean --windowed --name Loonify ^
  --icon icon.ico --add-data "ui.html;." --add-data "icon.ico;." ^
  --collect-all ytmusicapi --collect-all yt_dlp --collect-all webview ^
  --collect-submodules yandex_music --collect-submodules spotipy ^
  app.py || goto :err

echo [3/3] Создание установщика...
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" (
  echo.
  echo Inno Setup не найден, поэтому готов только сам exe:
  echo   %~dp0dist\Loonify\Loonify.exe
  echo Чтобы получить Loonify_Setup.exe, установите Inno Setup 6 ^(https://jrsoftware.org/isdl.php^)
  echo и запустите build.bat ещё раз.
  pause & exit /b 0
)
"%ISCC%" installer.iss || goto :err
echo.
echo ГОТОВО: %~dp0Output\Loonify_Setup.exe
pause & exit /b 0

:err
echo.
echo ОШИБКА. Скопируйте текст выше и отправьте мне.
pause & exit /b 1
