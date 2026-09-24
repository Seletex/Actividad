# Despliegue en Render (web con PostgreSQL) — Guía paso a paso

Este documento explica cómo publicar la **app web "Gestión de Actividades"** en
[Render](https://render.com) usando **PostgreSQL**, y cómo usar los dos scripts
nuevos para subir datos y configurar el primer acceso.

> Todo el trabajo se hace **desde tu máquina local**. La app corre en Render
> con una base de datos PostgreSQL (`DATABASE_URL`), mientras que en local
> sigue usando el SQLite (`actividades.db`).

---

## 1. Antes de empezar (requisitos)

- Tener una cuenta en [render.com](https://render.com) (plan gratuito vale).
- Tener Git instalado y el proyecto versionado (`git` ya inicializado en este repo).
- **No olvides confirmar que tus cambios estén commiteados** antes de desplegar:

```
git status
git add .
git commit -m "Flujo admin asigna contrasena + scripts de despliegue"
```

---

## 2. Crear la base de datos PostgreSQL en Render

1. Inicia sesión en Render y entra en el panel.
2. Crea una **PostgreSQL** (Database):
   - Nombre: `actividades-db`
   - **Plan: Free** (ROI de prueba).
3. Cuando se cree, Render te mostrará la **Connection String** (Internal
   Database URL). **Cópiala y guárdala**, la necesitarás para subir datos
   (paso opcional 5). Se ve así:

```
postgresql://actividadesdb_user:XXXXXXXX@dpg-XXXX-a.oregon-postgres.render.com/actividadesdb
```

> Render carga la app con la opción "Connect to an existing database" y este
> archivo `render.yaml`; pero si creas la web manualmente, pega allí esta URL.

---

## 3. Crear el servicio web (la app)

Opciones:

### A) Usando `render.yaml` (Blueprints) — recomendado

El archivo `render.yaml` ya está preparado. En Render crea un **Blueprint** y
selecciona este repositorio. Render creará **juntas** la base (`actividades-db`)
y el servicio web (`actividades-app`) con:

- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --config gunicorn_config.py`
- Entorno: `DATABASE_URL` (desde la BD) + `FLASK_SECRET_KEY` (auto) + `PYTHON_VERSION=3.11.0`

### B) Manual

1. **New → Web Service**, conecta tu repositorio.
2. Configura:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --config gunicorn_config.py`
   - **Environment Variables**:
     - `PYTHON_VERSION` = `3.11.0`
3. Ve a tu instancia de `actividades-db` → **Connect** → copia la *Internal
   Database URL* y créala como variable de entorno `DATABASE_URL` en el web service.
4. Añade también `FLASK_SECRET_KEY` (Render puede generarla automáticamente).

> `requirements.txt` ya incluye `psycopg2-binary`, `flask`, `gunicorn`, `pandas`,
> `openpyxl` y `fpdf`. La app detecta `DATABASE_URL` y usa PostgreSQL; en
> local, sin esa variable, usa SQLite. **No necesitas subir `actividades.db`**:
> Render crea las tablas al arrancar (`inicializar_usuarios`, etc.).

---

## 4. Desplegar y verificar

1. Reinicia/manual **Deploy** en Render (o hace deploy automático al hacer push).
2. Abre la URL que Render te asigne (ej. `https://actividades-app.onrender.com`).
3. Verifica que arranca sin errores en el panel de logs.

> En esta primera versión la tabla **usuarios** queda vacía (solo con el usuario
> `admin` sin contraseña), igual que en local. No definas contraseñas web a mano:
> usa `setup_admin.py` (paso 5) y la pantalla web de administración.

---

## 5. Script `setup_admin.py` — configurar la contraseña del admin

Configura la contraseña del usuario `admin` (con hash PBKDF2 y opción de forzar
cambio en el primer ingreso). **Debe ejecutarse contra la BD que se quiera
afectar** (local o la de Render).

### En local (usuario admin local / LAN):

```
python setup_admin.py
```

### Contra la BD de Render (desde tu máquina):

```
set DATABASE_URL=postgresql://usuario:clave@host/db
python setup_admin.py
```
(PowerShell: `$env:DATABASE_URL="postgresql://..."`)

El script:
- Pide la contraseña (oculta, por `getpass`) y valida ≥ 6 caracteres.
- Pregunta si quieres **forzar el cambio en el primer ingreso**.
- Guarda usuario y contraseña y verifica las credenciales.

---

## 6. Script `sync_db_to_postgres.py` — subir los datos locales a la web (OPCIONAL pero recomendado)

Copia los datos del SQLite local (`usuarios`, `registros`, `listas`, config,
bitácora) hacia el PostgreSQL de Render.

```
set DATABASE_URL=postgresql://usuario:clave@host/db
python sync_db_to_postgres.py
```
(PowerShell: `$env:DATABASE_URL="postgresql://..."; python sync_db_to_postgres.py`)

Opciones:
- `--modo merge` (por defecto): inserta/actualiza sin borrar lo existente en la web.
- `--modo reemplazar`: limpia y reinserta (pide confirmación).
- `--modo vacio`: solo agrega lo que no exista.
- `--tablas usuarios,registros` : migra solo esas.
- `--local "ruta\actividades.db"` : apunta a otro SQLite.

> **Antes de migrar**, decide si quieres subir las contraseñas ya asignadas en
> local. Si quieres que los usuarios entren igual en la web, migra la tabla
> `usuarios` completa (incluye `password_hash`/`salt`, por lo que los logins
> locales sirven en la web). Si esperas que cada usuario configure su clave en
> la web, ejecuta `sync` **sin** la tabla `usuarios` o con usuarios sin contraseña.

---

## 7. Primer uso en la web

1. Entra con el usuario `admin` y la contraseña que definiste con `setup_admin.py`.
2. En **Gestión de usuarios** (menú de administración) verás, por usuario, un
   badge de estado: *Sin contraseña / Configurada / Debe cambiar / Administrador*.
3. Asigna a cada usuario su contraseña (campo + casilla **"Forzar"** si quieres
   que la cambie en el primer ingreso).
4. Cada usuario entra con la contraseña asignada; si marcaste "Forzar", la app
   lo obligará a poner una propia antes de usar el sistema.

---

## Notas y advertencias

- **Nunca** subas `actividades.db` a un repositorio público; contiene datos de la
  municipalidad. `render.yaml` y la app usan PostgreSQL en la web por eso.
- `FLASK_SECRET_KEY` y `DATABASE_URL` son sensibles: Render los gestiona como
  variables de entorno; no los pongas en código.
- `pythonanywhere_update.py` es para el despliegue antiguo de PythonAnywhere; no
  aplica al objetivo actual (Render + PostgreSQL).

---

## Resumen rápido de comandos

| Tarea | Comando (local) |
|-------|-----------------|
| Commit | `git add . ; git commit -m "Despliegue web"` |
| Push a Render | `git push origin main` |
| Configurar admin (local) | `python setup_admin.py` |
| Configurar admin (web) | `set DATABASE_URL=<url>` + `python setup_admin.py` |
| Subir datos a la web | `set DATABASE_URL=<url>` + `python sync_db_to_postgres.py` |
