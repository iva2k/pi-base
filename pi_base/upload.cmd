:: Upload all files in this folder to remote host over SSH / SCP

@echo off
setlocal enableextensions enabledelayedexpansion
set me=%~n0
set parent=%~dp0
set parent=%parent:~0,-1%  && rem ## trim trailing slash

set interactive=0
echo %CMDCMDLINE% | findstr /L /I %COMSPEC% >NUL 2>&1
if %ERRORLEVEL% == 0 set interactive=1

set "SOURCE=%parent%"
for %%F in ("%SOURCE%") do set "SOURCE_NAME=%%~nxF"
for %%F in ("%SOURCE%") do set "SOURCE_PARENT=%%~dpF"

set cmd=scp
set u=pi
::set host=raspberrypi
set host=rpi
set host_dir=
:params

rem ## unquote: %~1%
set a=%~1%

if "%a%"=="" goto endparams
if "%a%"=="--user"    (set "u=%~2" & shift & shift & goto params)
if "%a%"=="--host"    (set "host=%~2" & shift & shift & goto params)
rem if "%a%"=="--host_dir"     (set "host_dir=%~2%" & shift & shift & goto params)
if "%a%"=="--path"    (set "host_dir=%~2" & shift & shift & goto params)
if "%a%"=="--cmd"     (set "cmd=%~2" & shift & shift & goto params)
if "%a%"=="ssh_remove_key"  (shift & shift & call :ssh_remove_key "%~2" & goto eof)
::if "%a%"=="build"     (shift & set clean=0 & set build=1 & set doinstall=0 & goto params)

goto usage
:endparams

rem if [%host_dir%] == [] (set host_dir=/home/%u%/%SOURCE% )
rem scp is finicky to create directory - seems to work only if not renaming the directory
if [%host_dir%] == [] (set host_dir=/home/%u%/ )

:: Debug:
::echo.DEBUG me=%me%
::echo.DEBUG parent=%parent%
::echo.DEBUG interactive=%intercative%
::echo.DEBUG _last_dir=%_last_dir%
::echo.DEBUG _parent_dir=%_parent_dir%
::echo.DEBUG SOURCE=%SOURCE%
::echo.DEBUG SOURCE_PARENT=%SOURCE_PARENT%
::echo.DEBUG SOURCE_NAME=%SOURCE_NAME%


:: Copy package to host
echo.Copying %SOURCE% directory to %host%:%host_dir%...
echo.Command:
echo.  cd %SOURCE_PARENT% ^&^& %cmd% -pr %SOURCE_NAME%/ %u%@%host%:%host_dir%
echo.
setlocal
  cd %SOURCE_PARENT% && %cmd% -pr %SOURCE_NAME%/ %u%@%host%:%host_dir%
endlocal

echo.
echo.DONE.

goto :eof

:usage
  echo Script usage is:
  echo     %me% [options]
  echo       Copy folder to remote host.
  echo:
  echo     %me% [options] ssh_remove_key [host]
  echo       Remove saved SSH host key
  echo:
  echo where [options] are:
  echo:
  echo:   --user ^<user_name^> (default "pi")
  echo:   --host ^<host_name_or_ip^> (default "%host%")
  echo:   --path ^<target_directory^> (default "/home/<user_name>/%SOURCE_NAME%")
  echo:   --cmd  ^<scp_command^> (default "scp")
  echo:
  echo For example:
  echo     %me%
  echo     %me% --user not_pi
  echo     %me% --host 10.1.2.3
goto :eof

:ssh_remove_key
  set "maybe_host=%~1"
  if "%maybe_host%"=="" set "maybe_host=%host%"
  ssh-keygen -R "%maybe_host%"
  echo:
goto :eof

:eof