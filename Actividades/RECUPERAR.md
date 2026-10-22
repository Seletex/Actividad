# Recuperar la aplicación después de la caída de la base de datos

> **Resumen en una línea:** la base de datos PostgreSQL gratuita de Render
> **cumplió 30 días y Render la eliminó por completo**, sin guardar copia.
> Nadie felló ninguna contraseña: la base ya no existía. Hay que crear una
> base nueva y volver a cargar los datos.

---

## 1. Qué pasó exactamente

| | Detalle |
|---|---|
| **Causa** | Las bases PostgreSQL **gratuitas de Render expiran 30 días después de crearse**. Pasado ese plazo (más 14 días de gracia) Render **elimina la base y todos sus datos**. |
| **Confirmación** | El log del servidor muestra: `could not translate host name "dpg-daop2bek1f9s7385ucug-a" to address: Name or service not known`. Ese nombre es el de la base: ya no existe. |
| **Por qué decía "Contraseña incorrecta"** | La app consultaba la base, la base no respondía, y ese error se mostraba como si fuera una clave equivocada. **Ya está corregido**: ahora dice *"El servicio está temporalmente fuera de servicio"* y **no** bloquea al equipo por intentos fallidos. |
| **Respaldo de Render** | La documentación de Render dice textualmente: *"Render does not retain backups or snapshots of a deleted database instance"*. **No hay copia en Render.** |
| **Fecha** | La base se creó el 22 de septiembre de 2026 y se eliminó el 22 de octubre de 2026 (exactamente 30 días). |

**Consecuencia importante:** todo lo que se cargó **en la web** entre el 29 de
septiembre y el 22 de octubre **se perdió**. No hay forma de recuperarlo.

**Lo que sí se conserva** (está en el equipo, intacto):

| Dato | Cantidad | Dónde |
|---|---|---|
| Registros de actividades | **1.605** | `%LOCALAPPDATA%\ActividadesData\actividades.db` |
| Usuarios | 7 | ídem |
| Actividades personales | 33 | ídem |
| Catálogos (ubicaciones, tipos, medios) | 81 | ídem |
| Configuración por usuario | 30 | ídem |
| Contraseñas (hashes) | **0** | *no existían fuera de la base eliminada* |

> Las contraseñas estaban **solo** dentro de la base que Render eliminó. Por eso
> hay que volver a asignarlas (paso 6). No es un error: es lo que la seguridad
> exige cuando se rehace una base desde cero.

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
4. **Región:** elige la más cercana a la de Render. Render usa `Oregon` →
   en Neon es **AWS us-west-2 (Oregon)**.
5. Neon crea la base al instante. Se abre la consola del proyecto.
6. **Guarda la contraseña**: en la esquina superior derecha, el ícono de
   contraseña / *Reset password*. Sin ella no hay conexión.
7. Abajo a la izquierda, en el panel **Connection details** (o *Connect*):
   - Copia la **Connection string**.
   - **Ojo: usa la de conexión DIRECTA, no la "pooled".**
     La directa se ve así:
     ```
     postgresql://neondb_owner:TU_CONTRASEÑA@ep-xxxx-yyy.us-west-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
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

## 6. Reasignar las contraseñas de los usuarios

Las contraseñas **no se pudieron recuperar** (vivían solo en la base
eliminada). Hay que volver a asignarlas:

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
La copia útil tiene que salir de la nube. Para eso está `respaldar_automatico.py`:

```powershell
python respaldar_automatico.py `
  --url "postgresql://LA_CONNECTION_STRING_DE_NEON" `
  --destino "\\192.168.10.2\respaldos_actividades"
```

Genera un ZIP con registros, usuarios, configuración y catálogos, y conserva
los 30 últimos. Para que se ejecute solo:

1. Windows → **Programador de tareas** → **Crear tarea**.
2. **General**: nombre `Respaldo Actividades`, *Ejecutar solo si el usuario
   está conectado*.
3. **Desencadenadores** → **Nuevo** → *Diariamente* → 22:00.
4. **Acciones** → *Iniciar un programa*:
   - Programa: `C:\Users\apoyosistemas\AppData\Local\Programs\Python\Python312\python.exe`
   - Argumentos: `"C:\Users\apoyosistemas\Documents\GitDesk\Actividad\Actividades\respaldar_automatico.py" --url "postgresql://..." --destino "\\192.168.10.2\respaldos_actividades"`
   - Iniciar en: `C:\Users\apoyosistemas\Documents\GitDesk\Actividad\Actividades`

Con eso, aunque la base se perdiera otra vez, se recupera en minutos.

### 8.2 Respaldo instantáneo dentro de Neon (gratis)

Neon permite crear una **ramificación** (*branch*): una copia de la base que
comparte el almacenamiento (no ocupa el doble de espacio).

1. Consola de Neon → proyecto **actividades** → **Branches**.
2. **Create branch** → nombre `respaldo-2026-10-22` (o la fecha del día).
3. Para restaurar: en esa ramificación, *Reset* / *Promote* → de vuelta a `main`.

Es una segunda red de seguridad, sin coste y en dos clics. Conviene crear una
ramificación **antes** de cualquier importación masiva o cambio grande.

### 8.3 Lo que de verdad evita la repetición

Que la base **no sea la gratuita de Render**: esa caduca a los 30 días y Render
elimina los datos sin dejar copia. Con **Neon** la base no se borra nunca; a lo
sumo el cómputo se apaga por inactividad y se vuelve a encender solo.

El respaldo automático (8.1) y las ramificaciones (8.2) son la red de seguridad
para lo que sí puede fallar: un error de importación, un borrado accidental.

### 8.4 Comprobaciones que ya están dentro de la aplicación

- `/salud` dice si la base responde (no hace falta entrar con clave).
- La caída de la base **no** muestra "Contraseña incorrecta" ni bloquea la IP.
- El respaldo que genera la web se puede descargar en cualquier momento desde
  *Gestión → Descargar respaldo ZIP*.
