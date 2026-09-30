@echo off
echo Iniciando Servidor Web seguro de Actividades...
echo Por favor espere...
start http://localhost:8000
pushd "%~dp0"
python Actividades\app.py
popd
pause
