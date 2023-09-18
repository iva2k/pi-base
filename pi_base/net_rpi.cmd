@echo off

echo.
echo This script connects Samba Shares from Raspberry Pi to Windows drives
echo For Samba to be active, install.sh in one of subdirs should be run first on the target RPi.
echo.

::set SERVER=PI-SPI
set SERVER=RPI
set SERVER_USER=pi

:: Set SERVER_LC to a value of %SERVER% converted to lowercase
set LowerCaseMacro=for /L %%n in (1 1 2) do if %%n==2 (for %%# in (a b c d e f g h i j k l m n o p q r s t u v w x y z) do set "SERVER_LC=!SERVER_LC:%%#=%%#!") else setlocal enableDelayedExpansion ^& set SERVER_LC=
%LowerCaseMacro%%SERVER%

::? set NETUSER=%SERVER_LC%\%SERVER_USER%
set NETUSER=%SERVER%\%SERVER_USER%

set /p PASSWD=Enter password for %NETUSER% on %SERVER% server: 

cmdkey /add:%SERVER% /user:%NETUSER% /pass:%PASSWD%

echo Removing existing connections...
::net use Z: /delete
net use Y: /delete
net session \\%SERVER% /delete

:: List of drives to connect:
call :add_netdrive Z \\%SERVER_LC%\pi %NETUSER% %PASSWD%
call :add_netdrive Y \\%SERVER_LC%\share %NETUSER% %PASSWD%

pause
goto :eof

:add_netdrive
  set drive=%1
  set uri=%2
  set user=%3
  set pass=%4
  echo Connecting %uri% to %drive%: (as user %user%)...
  net use %drive%: %uri% %pass% /persistent:yes /user:%user%
  reg add "HKEY_CURRENT_USER\Network\%drive%" /v "DeferFlags" /t REG_DWORD /d 4 /f
goto :eof
