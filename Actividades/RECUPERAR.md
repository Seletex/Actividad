# Recuperar la aplicación después de la caída de la base de datos

> **Resumen en una línea:** la base de datos PostgreSQL gratuita de Render
> **cumplió 30 días y quedó suspendida** (no borrada): durante **14 días** se
> puede reactivar pagando un mes (~7 USD) y **rescatar todo** lo que se cargó
> en la web. La solución definitiva ya está funcionando en **Neon**, que no
> caduca.

---

## 1. Qué pasó exactamente

| | Detalle |
|---|---|
| **Causa** | Las bases PostgreSQL **gratuitas de Render expiran 30 días después de crearse**. Al expirar quedan **inaccesibles**, pero **no se borran**. |
| **Plazo de gracia** | Render da **14 días** desde la expiración para pasar la base a un plan de pago. **Después de ese plazo sí la borra con todos sus datos**, y no guarda copia. |
| **Confirmación** | El log del servidor muestra: `could not translate host name "dpg-daop2bek1f9s7385ucug-a" to address: Name or service not known`. Ese nombre es el de la base: está **suspendida** (el panel de Render la muestra como *Suspended*), no eliminada. |
| **Por qué decía "Contraseña incorrecta"** | La app consultaba la base, la base no respondía, y ese error se mostraba como si fuera una clave equivocada. **Ya está corregido**: ahora dice *"El servicio está temporalmente fuera de servicio"* y **no** bloquea al equipo por intentos fallidos. |
| **Respaldo de Render** | El plan gratuito **no tiene ningún tipo de copia**. La documentación de Render lo dice textual: *"Free Render Postgres databases don't support any form of backups"*. |
| **Fecha** | Se creó el 22/09/2026 y caducó el 22/10/2026 (30 días). **Periodo de gracia: hasta el ~05/11/2026.** |

**Qué está en juego:** lo que se cargó **en la web** entre el 29 de septiembre y
el 22 de octubre **todavía se puede rescatar**, pero solo hasta el **~5 de
noviembre**: hay que reactivar la base de Render con un plan de pago y copiar
sus datos a Neon (ver **paso 5 bis**). Pasada esa fecha, se pierde para siempre:
Render la borra y no conserva copia.

**Lo que ya está a salvo** en Neon y en el equipo:

| Dato | Cantidad | Dónde |
|---|---|---|
| Registros de actividades | **1.605** | `%LOCALAPPDATA%\ActividadesData\actividades.db` |
| Usuarios | 7 | ídem |
| Actividades personales | 33 | ídem |
| Catálogos (ubicaciones, tipos, medios) | 81 | ídem |
| Configuración por usuario | 30 | ídem |
| Contraseñas (hashes) | **0** | *estaban solo dentro de la base de Render* |

> Las contraseñas originales están **solo** dentro de la base de Render. Si se
> hace el rescate del paso 5 bis, **vuelven a funcionar tal cual** (se copian
> los hashes). Si no se hace, hay que asignar claves nuevas desde la web
> (paso 6): al rehacer la base desde la copia local no hay ninguna contraseña
> que reutilizar, y eso es lo correcto por seguridad.

---

## 2. Decisión tomada: base de datos en Neon (gratis)

La base gratuita de Render **vuelve a caducar en 30 días**, así que se cambió
de proveedor. La decisión es:

### Neon — plan gratuito (elegido) ✅

- [neon.com](https://neon.com) → cuenta gratuita (0,5 GB, suficiente de sobra).
- **No caduca nunca**: si el proyecto queda inactivo, el *cómputo* se apaga,
  pero **los datos siguen ahí** intactos. Se vuelve a encender solo en el
  siguiente acceso.
- Conexión cifrada por SSL obligatoria (Neon no acepta conexiones sin cifrar).
- **Ramificaciones:** se puede crear una copia de la base en un clic
  ("Create branch"), que sirve de respaldo instantáneo sin coste.
- Cambia **una sola cosa**: la variable `DATABASE_URL`.

> Lo descartado: **Render PostgreSQL de pago** (plan *Starter*, 7 USD/mes) era
> la opción más cómoda porque todo queda en el mismo panel, pero requiere
> tarjeta. Si más adelante hay presupuesto, migrar de Neon a Render de pago es
> cambiar de nuevo la misma variable `DATABASE_URL`, sin tocar el código.

> La aplicación **no cambia ni una línea de código**: todo depende de
> `DATABASE_URL`.

---

## 3. Crear la base de datos nueva en Neon (gratis)

1. Entra en [neon.com](https://neon.com) y crea una cuenta (correo o Google).
2. Neon abre una pantalla de bienvenida: **Create a project** (o "Plan free").
3. Nombre del proyecto: `actividades`.
4. **Región:** cualquiera cercana sirve. El proyecto actual está en
   **AWS us-east-2 (Ohio)**; se reconoce porque la cadena de conexión lleva
   `c-7.us-east-2.aws.neon.tech`.
5. Neon crea la base al instante. Se abre la consola del proyecto.
6. **Guarda la contraseña**: en la esquina superior derecha, el ícono de
   contraseña / *Reset password*. Sin ella no hay conexión.
7. Abajo a la izquierda, en el panel **Connection details** (o *Connect*):
   - Copia la **Connection string**.
   - **Ojo: usa la de conexión DIRECTA, no la "pooled".**
     La directa se ve así:
     ```
     postgresql://neondb_owner:TU_CONTRASEÑA@ep-xxxx-yyy.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
     ```
     La "pooled" lleva `-pooler` en el nombre del servidor: **no sirve** para
     la aplicación web (ese proxy está pensado para conexiones efímeras
     de servidores sin estado).

> **La contraseña de Neon contiene caracteres especiales.** Si la copias a
> mano, asegúrese de que no falte ninguno. Lo más seguro es usar el botón
> *Copy* y pegarla entera.

---

## 4. Conectar la base de Neon con la aplicación en Render

1. En el panel de Render, abre tu **Web Service** (la aplicación web).
2. Ve a **Environment** (variables de entorno).
3. Sustituye el valor de `DATABASE_URL` por la **Connection string directa**
   de Neon (la del punto 7 del paso anterior).
4. Comprueba que estas variables siguen ahí:
   - `FLASK_SECRET_KEY` — **no la cambies**: si la cambias, se caen las sesiones
     abiertas de todos (no es grave, pero molesta).
   - `PYTHON_VERSION` = `3.11.0`
   - `ADMIN_INITIAL_PASSWORD` — ponle una clave temporal **solo para el primer
     ingreso**. **Bórrala en cuanto entres** (más abajo se explica).
5. Pulsa **Save Changes** → Render **redespliega** automáticamente.
   > Si no se redespliega solo, ve a la página del servicio → **Manual Deploy →
   > Deploy latest commit**.
6. Comprueba el estado en <https://actividad-0c88.onrender.com/salud>. Debe
   responder algo como:
   `{"servicio": "ok", "base_datos": "ok", "registros": 0}`
   Si dice `"base_datos": "no disponible"`, la URL no está bien pegada.

> **Sobre `ADMIN_INITIAL_PASSWORD`:** es una contraseña temporal para el
> administrador que la aplicación aplica **solo si el usuario `admin` todavía no
> tiene clave**. Sirve para poder entrar a una base recién creada. En cuanto
> entre, **bórrela del panel de Render** (Environment → `ADMIN_INITIAL_PASSWORD`
> → *Remove* → Save Changes). Si se queda ahí, cualquiera que lo descubra
> podría tomar el control.

---

## 5. Restaurar los datos

### Opción recomendada — desde este equipo (un solo comando)

La herramienta `restaurar_produccion.py` copia **todo** desde la base local
(registros, usuarios, actividades, catálogos y configuración) y verifica que
todo haya quedado bien.

1. Vuelve a la consola de Neon → **Connection details** → copia la
   **Connection string directa** (la misma que pegaste en `DATABASE_URL`).
   > Termina en `?sslmode=require&channel_binding=require`. **Déjelo tal cual**:
   > es lo que Neon exige para aceptar la conexión y mantiene el tráfico
   > cifrado. Si la URL va entre comillas en PowerShell, no la partas.
2. Abre **PowerShell** en la carpeta `Actividades` del proyecto y ejecuta:

```powershell
cd "C:\Users\apoyosistemas\Documents\GitDesk\Actividad\Actividades"

python restaurar_produccion.py `
  --url "postgresql://PEGA_AQUI_LA_CONNECTION_STRING_DE_NEON" `
  --local "$env:LOCALAPPDATA\ActividadesData\actividades.db" `
  --contrasena-admin "UnaClaveFuerteParaElAdmin" `
  --forzar-cambio-admin
```

3. Debe mostrar:

```
  usuarios                        7 fila(s) copiada(s)
  actividades_personales         33 fila(s) copiada(s)
  configuracion_usuario           30 fila(s) copiada(s)
  listas_globales                81 fila(s) copiada(s)
  registros                    1605 fila(s) copiada(s)
```

### Opción alternativa — desde el navegador (sin ejecutar nada)

Si no puede ejecutar el comando anterior, se puede hacer todo desde la web
con el usuario `admin`:

1. **Reemplazar todos los registros** → subir un `.xlsx` con los 1.605
   registros. (El archivo `actividades_migracion_1605_20260929.xlsx` sirve, pero
   lo más fiel es generarlo desde la base local con `respaldar_automatico.py`.)
2. **Sincronizar datos de usuarios** → subir el `usuarios.json` que incluye
   usuarios, actividades personales, configuración **y los catálogos**.

> **Aviso:** hasta esta versión, esa segunda pantalla **perdía el catálogo de
> ubicaciones** (el respaldo lo guarda como `ubicaciones` y el importador solo
> leía `dependencias`). Ya está corregido y cubierto por pruebas automáticas.

---

## 5 bis. Rescatar lo cargado en la web (base de Render suspendida)

Esto **solo se puede hacer hasta el ~5 de noviembre de 2026**. Sirve para
recuperar lo que se registró en la web entre el 29/09 y el 22/10, que no está en
la copia local. Cuesta **un mes del plan más pequeño** (unos 7 USD) y luego la
base de Render se puede borrar.

### Paso 1 — Reactivar la base en Render

1. Entra en [dashboard.render.com](https://dashboard.render.com) → **Databases**
   (no en el *Web Service*).
2. Abre la base que aparece como **Suspended** (`dpg-daop2bek1f9s7385ucug-a`).
3. Pulsa **Upgrade** / **Change plan** y elige el plan de pago **más pequeño**.
   Si pide tarjeta, se agrega en **Billing**.
4. Espera a que el estado cambie a **Available** (1–3 minutos).

> ⚠️ No pulses **Delete** y no crees otra base: solo el *upgrade* reactiva esta.

### Paso 2 — Copiar todo de Render a Neon (una sola orden)

En Render, dentro de la base → **Connect** (o *Info*) → copia la
**External Database URL**. Es una línea larga; debe llevar el `@` antes del
servidor.

Desde este equipo, en la carpeta `Actividades`:

```powershell
python fusionar_bases.py `
  --origen "PEGAR_AQUI_LA_URL_DE_RENDER" `
  --destino "postgresql://neondb_owner:CONTRASENA@ep-dark-snow-b51vh3lp.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require" `
  --contrasena-admin "UnaClaveTemporalParaElAdmin"
```

Qué hace la herramienta, en orden:

| Tabla | Qué pasa |
|---|---|
| `registros` | Se copian **todos** los de Render (es la base que estuvo en producción). **Si Render tuviera menos registros que Neon, se detiene sin tocar nada** (protección contra borrados accidentales). |
| `usuarios` | Se copian los **hashes originales**: las contraseñas de antes vuelven a funcionar. |
| `actividades_personales`, `listas_globales` | Se unen sin duplicar. |
| `configuracion_usuario` | Se queda la de Render. |
| Sesiones y auditoría | **No se copian**: todas las sesiones abiertas quedan cerradas. |

Debe terminar con algo así:

```
  registros                1.6xx
  usuarios                 7
  actividades_personales   33
  configuracion_usuario    30
  listas_globales          81
  usuarios con contrasena: 7 de 7
Fusion completada.
```

### Paso 3 — Verificar y borrar la base de Render

1. Abre `https://actividad-0c88.onrender.com/salud`: debe responder
   `"base_datos": "ok"` con el número de registros actualizado.
2. Entra a la web con tu **contraseña de antes** (la original). Si no la
   recuerdas, usa la que se pasó en `--contrasena-admin`; la app pedirá
   cambiarla.
3. Comprueba que aparecen los registros de octubre.
4. **Borra la base de Render** (Database → Settings → Delete) para no seguir
   pagando. Neon ya tiene todo.

> La herramienta se puede volver a ejecutar sin miedo: no duplica nada. Y si se
> ejecuta por error con las bases invertidas, el control de conteo la detiene
> antes de escribir.

---

## 6. Reasignar las contraseñas de los usuarios

Si **no** se hizo el rescate del paso 5 bis, las contraseñas originales no
existen en ningún sitio: hay que volver a asignarlas.

1. Entra en la web como `admin` con la clave de `ADMIN_INITIAL_PASSWORD`.
2. La aplicación te pedirá cambiar la contraseña del administrador: pon una
   nueva y **no la compartas con nadie**.
3. Ve a **Gestión → Usuarios del Sistema**.
4. Para cada uno de los 6 usuarios (Alejandro, Claudia, Felipe, Freddy, JuanB,
   Manolo): escribe una clave temporal y marca **"Forzar cambio"**.
5. Cada usuario entra con esa clave temporal y la aplicación le obliga a crear
   la suya. Nadie conoce la clave de los demás.

> Este paso es de seguridad: cada usuario debe recibir su contraseña temporal
> por un canal seguro (no por un chat grupal donde todos la puedan leer).

---

## 7. Verificar que todo quedó bien

| Comprobación | Cómo |
|---|---|
| La base responde | Abrir `/salud` (no hace falta entrar con clave) → `"base_datos": "ok"` |
| Hay 1.605 registros | `/salud` → `"registros": 1605` |
| Los 7 usuarios existen | Gestión → Usuarios del Sistema |
| Los catálogos están completos | Gestión → Listas (ubicaciones, tipos, medios) |
| Un usuario entra y registra | Entrar con su clave temporal y crear una actividad de prueba |

---

## 8. Evitar que vuelva a pasar

### 8.1 Respaldo automático diario hacia este equipo

La aplicación web corre en un disco **efímero** (se pierde en cada
redespliegue), así que un respaldo guardado dentro de Render no sirve de nada.
La copia útil tiene que salir de la nube. Para eso está `respaldar_automatico.py`,
que genera un ZIP con:

- `base_completa.sql`: volcado completo hecho con `pg_dump` (registros,
  usuarios **con sus contraseñas**, bitácora y sesiones). Es la copia que
  permite restaurar todo tal como estaba.
- `registros.csv`, `usuarios.json` y `manifiesto.json`: copia legible de los
  datos operativos, para Excel o para reimportar desde la web.
- `LEEME.txt`: instrucciones de restauración.

Conserva los últimos 60 respaldos.

**Instalación actual (26/10/2026).** No se guarda la URL en la tarea: la
contiene un lanzador local, fuera del repositorio y de Git.

| Elemento | Valor |
|---|---|
| Tarea de Windows | `Actividades - Respaldo diario` |
| Hora | Todos los días a las 18:00 (si el PC estaba apagado, corre al encender) |
| Lanzador | `%LOCALAPPDATA%\ActividadesData\respaldo_diario_actividades.cmd` |
| Destino | `C:\Users\apoyosistemas\Documents\Documentos\Respaldo` (lo replica el NAS) |
| Registro | `%LOCALAPPDATA%\ActividadesData\respaldo_actividades.log` |
| Retención | 60 respaldos |

El lanzador contiene la cadena de conexión de Neon. **Si se rota la contraseña
de Neon, hay que actualizarla en ese archivo**; si no, el respaldo fallará y
dejará el error en el registro.

Para probarlo a mano: doble clic en el lanzador, o

```powershell
Start-ScheduledTask -TaskName "Actividades - Respaldo diario"
Get-Content "$env:LOCALAPPDATA\ActividadesData\respaldo_actividades.log" -Tail 10
```

También se puede ejecutar suelto, por ejemplo antes de una importación grande:

```powershell
python respaldar_automatico.py `
  --url "postgresql://LA_CONNECTION_STRING_DE_NEON" `
  --destino "C:\Users\apoyosistemas\Documents\Documentos\Respaldo"
```

Con `--sin-dump` se omite `base_completa.sql` y el ZIP no lleva contraseñas.
Si `pg_dump` no está en el equipo, el respaldo se genera igual, sin la copia
completa, y lo avisa en el registro.

**Restauración completa** en una base nueva o vacía:

```powershell
psql "postgresql://usuario:clave@servidor/base" -f base_completa.sql
```

El SQL se generó con `--clean --if-exists`, así que también se puede cargar
sobre una base existente: reemplaza las tablas de la aplicación.

### 8.2 Respaldo instantáneo dentro de Neon (gratis)

Neon permite crear una **ramificación** (*branch*): una copia de la base que
comparte el almacenamiento (no ocupa el doble de espacio).

1. Consola de Neon → proyecto **actividades** → **Branches**.
2. **Create branch** → nombre `respaldo-2026-10-22` (o la fecha del día).
3. Para restaurar: en esa ramificación, *Reset* / *Promote* → de vuelta a `main`.

Es una segunda red de seguridad, sin coste y en dos clics. Conviene crear una
ramificación **antes** de cualquier importación masiva o cambio grande.

### 8.3 Lo que de verdad evita la repetición

Que la base **no sea la gratuita de Render**: esa caduca a los 30 días; al
caducar queda suspendida y solo se recupera pagando dentro de los **14 días**
siguientes, y pasado ese plazo Render borra los datos sin dejar copia. Con
**Neon** la base no se borra nunca; a lo sumo el cómputo se apaga por
inactividad y se vuelve a encender solo.

El respaldo automático (8.1) y las ramificaciones (8.2) son la red de seguridad
para lo que sí puede fallar: un error de importación, un borrado accidental.

### 8.4 Comprobaciones que ya están dentro de la aplicación

- `/salud` dice si la base responde (no hace falta entrar con clave).
- La caída de la base **no** muestra "Contraseña incorrecta" ni bloquea la IP.
- El respaldo que genera la web se puede descargar en cualquier momento desde
  *Gestión → Descargar respaldo ZIP*.

### 8.5 Subir las actividades que quedaron solo en un equipo

Cuando la conexión falla, la aplicación sigue guardando en el `actividades.db`
de cada equipo. Para traer esas actividades a Neon sin repetir las que ya están:

```powershell
cd C:\Users\apoyosistemas\Documents\GitDesk\Actividad\Actividades
$env:DATABASE_URL="postgresql://LA_CONNECTION_STRING_DE_NEON"

# 1) Ensayo: solo informa, no escribe nada
python importar_faltantes.py --carpeta "C:\Escaner"

# 2) Subida real (antes crea un respaldo con pg_dump)
python importar_faltantes.py --carpeta "C:\Escaner" --aplicar
```

Se revisan las subcarpetas `Manolo`, `Juan` y `Freddy`. La comparación ignora
mayúsculas, tildes y espacios de más, compara la fecha por día y respeta la
cantidad (si el equipo tiene dos iguales y la nube una, sube una). Al terminar
comprueba que ya no falte nada y avisa si queda algún registro.

Si un registro ya está en Neon con otro texto, se puede dejar fuera:

```powershell
python importar_faltantes.py --carpeta "C:\Escaner" --aplicar --excluir "Freddy:3950"
```

Las carpetas se pueden cambiar con `--usuario "Carpeta=Usuario"` y el destino
del respaldo previo con `--destino-respaldo`.
