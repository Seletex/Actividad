# Sistema de Actividades — Versión PHP para 260mb.net

Esta carpeta contiene una copia independiente del sistema de actividades,
hecha en PHP y MySQL para publicarla en el hosting **260mb.net**. No necesita
Python, Flask, Neon ni Composer: solo el hosting con PHP y una base de datos
MySQL.

La copia incluye los **1.901 registros activos**, los 7 usuarios, los catálogos,
las actividades personales y las configuraciones que tiene la aplicación
actual. Las actividades que estaban cortadas ya fueron reparadas. La copia se
generó el 9 de noviembre de 2026.

> Importante: este paquete contiene datos personales y contraseñas. Guárdelo
> en un lugar seguro y no lo comparta por correo ni por mensajería.

---

## 1. Qué necesita el hosting

- PHP **7.4 o superior** (se recomienda PHP 8.1, 8.2 u 8.3).
- MySQL o MariaDB.
- Las extensiones de PHP: `pdo_mysql`, `mbstring`, `zip`, `curl` y `json`.
  Casi todos los hostings las traen activas.
- Apache con `.htaccess` (260mb.net lo usa). Si el hosting usara Nginx, habría
  que proteger las carpetas `datos/` y `sql/` desde el panel.

## 2. Archivos importantes

| Archivo | Para qué sirve |
|---|---|
| `index.php` | Página principal y todas las rutas del sistema. |
| `ticket.php` | Mesa de ayuda (tickets). |
| `respaldo.php` | Copia los datos de Render a MySQL y permite devolver cambios si hubo una caída. |
| `instalar.php` | Crea las tablas y carga la copia de datos. Se borra al terminar. |
| `config.php` | Configuración general. |
| `config.local.php` | Datos reales de MySQL y notificaciones. **No lo comparta.** |
| `datos/datos_iniciales.json` | Copia de los datos actuales. Se carga desde el instalador. |
| `sql/datos_iniciales.sql` | La misma copia, para importar con phpMyAdmin si se prefiere. |
| `sql/esquema_mysql.sql` | Solo las tablas vacías, sin datos. |
| `LEEME.md` | Este instructivo. |

## 3. Instalación paso a paso

### Paso 1. Descargue y descomprima

Descargue el archivo `php_260mb_deploy.zip` y descomprímalo en su equipo.
Verá las carpetas `datos`, `lib`, `sql`, `views` y los archivos `index.php`,
`instalar.php`, `config.php`, `config.local.php`, entre otros.

### Paso 2. Suba los archivos al hosting

1. Entre al panel de 260mb.net.
2. Abra el **Administrador de archivos** (File Manager).
3. Entre a la carpeta pública del sitio, normalmente `public_html` o
   `htdocs`.
4. Suba el contenido del ZIP. Si el panel permite subir el ZIP y extraerlo,
   súbalo y use la opción **Extraer**.
5. Los archivos deben quedar directamente en la carpeta pública, no dentro de
   una carpeta adicional, salvo que quiera publicar el sistema en una
   subcarpeta (por ejemplo `public_html/actividades/`).

### Paso 3. Revise la conexión a MySQL

El archivo `config.local.php` ya viene con los datos de la base de 260mb.net:

- Servidor: `sql310.260mb.net`
- Base de datos: `n260m_43314047_actividades`
- Usuario: `n260m_43314047`
- Contraseña: está escrita dentro de `config.local.php`, en la línea `pass`.

Si cambió la contraseña de la base o creó otra base, edite
`config.local.php` y escriba los datos nuevos. La base debe existir antes de
instalar. Si no existe, créela desde el panel de 260mb.net (sección MySQL).

### Paso 4. Abra el instalador

En el navegador entre a:

```
https://su-dominio.260mb.net/instalar.php
```

o, si lo publicó en una subcarpeta:

```
https://su-dominio.260mb.net/actividades/instalar.php
```

### Paso 5. Complete el formulario

1. Escriba el usuario administrador (puede dejar `admin`).
2. Escriba una contraseña segura de **mínimo 6 caracteres**. Guárdela.
3. Deje marcada la opción **“Cargar también la copia de datos actual”**.
4. Pulse **Instalar**.

La instalación crea las tablas, los catálogos, el administrador y carga los
1.901 registros. Puede tardar entre uno y tres minutos. No cierre la pestaña
hasta que aparezca el mensaje **“Instalación terminada”**.

### Paso 6. Borre el instalador

Cuando termine, **borre o renombre `instalar.php`** desde el Administrador de
archivos. Mientras ese archivo exista, otra persona podría intentar instalar
de nuevo.

### Paso 7. Entre al sistema

Abra:

```
https://su-dominio.260mb.net/
```

Entre con el usuario y la contraseña que eligió en el Paso 5.

Los usuarios que venían de la aplicación anterior conservan la contraseña que
ya tenían. Si alguno no puede entrar, el administrador puede asignarle una
nueva en **Gestión → Usuarios**.

## 4. Cómo comprobar que quedó bien

1. Entre como administrador.
2. Abra **Registros** y confirme que aparecen los registros.
3. Abra **Exportar**, elija un rango de fechas y descargue un Excel. El texto
   de las actividades debe salir completo, sin cortarse.
4. Abra **Mi Gestión** y confirme que puede agregar una actividad personal.
5. Si algo falla, revise el archivo de errores de PHP del hosting.

## 5. Uso diario

- **Registros:** crear, buscar, editar y eliminar actividades.
- **Mi Gestión:** actividades personales, descargar pendientes, subir el Excel
  diligenciado y cambiar la contraseña.
- **Catálogos (solo administrador):** dependencias, tipos de solicitud, medios
  de solicitud y actividades globales.
- **Usuarios (solo administrador):** crear usuarios, asignar contraseñas y
  sincronizar desde un archivo `usuarios.json`.
- **Exportar:** informes detallados y finales en Excel o CSV.
- **Auditoría y Sesiones (solo administrador):** ver la bitácora y cerrar
  sesiones abiertas.
- **Mesa de ayuda:** tickets de soporte.
- **Respaldo:** el administrador puede descargar un ZIP con la base completa,
  los registros en CSV y un instructivo.

## 6. Seguridad y respaldos

- Use siempre **HTTPS**.
- Cambie la contraseña del administrador después de la primera entrada.
- No deje `instalar.php` en el hosting.
- Las carpetas `datos/` y `sql/` ya tienen un `.htaccess` que impide abrirlas
  desde el navegador. No borre esos archivos.
- El archivo `datos/datos_iniciales.json` contiene datos personales y
  contraseñas. Después de instalar, puede descargarlo a su equipo y borrarlo
  del hosting si no lo necesita; el sistema sigue funcionando.
- Descargue un respaldo desde **Gestión → Descargar respaldo** al menos una
  vez por semana. Guárdelo en el equipo o en la carpeta de respaldo.
- El ZIP de instalación también contiene datos personales y la contraseña de
  MySQL. No lo suba a GitHub ni lo comparta.

## 7. Respaldo automático desde Render (Neon)

Esta copia de 260mb.net puede recibir automáticamente los datos de Render
(actividades, usuarios, catálogos, configuraciones y tickets) y guardarlos en
MySQL. Así, si Render o la base Neon fallan, usted ya tiene aquí la información
del último respaldo y puede seguir trabajando.

### 7.1. Qué es un Cron Job

Un **Cron Job** es una alarma del hosting: una tarea que se ejecuta sola cada
cierto tiempo. No hay que dejar el programa abierto ni el computador encendido.

No es obligatorio tenerlo. Hay tres formas de programar el respaldo, de la más
cómoda a la más manual:

**Opción A. Cron Jobs del hosting (recomendada si 260mb.net la tiene).**

1. Entre al panel de 260mb.net.
2. Busque la sección **Cron Jobs** o **Tareas Cron**.
3. Cree una tarea nueva:
   - Frecuencia: **una vez al día**, por ejemplo a las **11:00 p.m.**
   - Comando:
     ```
     php /home/USUARIO/public_html/respaldo.php
     ```
     Cambie `USUARIO` y la ruta por los que muestre su panel. Algunos paneles
     piden la ruta completa de PHP, por ejemplo
     `/usr/local/bin/php /home/USUARIO/public_html/respaldo.php`.
4. Guarde la tarea.

**Opción B. cron-job.org (gratis, si el hosting no tiene Cron Jobs).**

1. Cree una cuenta gratis en `https://cron-job.org`.
2. Cree un trabajo nuevo que abra esta dirección **una vez al día**:
   ```
   https://su-dominio.260mb.net/respaldo.php?token=EL_TOKEN&accion=traer
   ```
3. Guarde el trabajo y active las notificaciones por correo para saber si falla.

Es un servicio externo que "entra" a esa dirección en el horario indicado. No
instala nada en su equipo.

**Opción C. Manual.**

Abra esa misma dirección en el navegador una vez al día, o al menos una vez por
semana, y pulse **Traer datos ahora**.

> **No programe el respaldo cada hora.** Render gratuito se duerme a los 15
> minutos sin uso. Si lo despierta cada hora, consume las 750 horas gratuitas
> del mes y los dos servicios se quedan sin cupo. Una vez al día es suficiente.

### 7.2. El token

El archivo `config.local.php` ya trae un token largo en la sección
`'respaldo'`. Ese mismo valor debe estar en Render, en la variable
**`RESPALDO_TOKEN`** del servicio `actividades-app`.

- El token es una contraseña: no lo comparta ni lo publique.
- Si lo cambia, cámbielo en los dos lugares.
- Si Render no tiene el token, el respaldo responde "no está configurado" y no
  entrega ningún dato.

### 7.3. Primera prueba

1. Suba esta versión a 260mb.net.
2. Abra en el navegador:
   ```
   https://su-dominio.260mb.net/respaldo.php?token=EL_TOKEN
   ```
3. Pulse **Traer datos ahora**. La primera copia puede tardar uno o tres
   minutos porque trae todos los registros.
4. Abajo verá la lista **Últimas sincronizaciones** con estado `ok` y el número
   de filas copiadas.

Repita la prueba un día después: la segunda copia debe ser más rápida y debe
decir cuántos registros actualizó.

### 7.4. Si Render se cae

1. Siga trabajando normalmente en 260mb.net. Todo lo que cree o modifique queda
   en MySQL.
2. Cuando Render vuelva, abra la página de respaldo.
3. Pulse **Enviar cambios a Render** y marque la casilla de confirmación.
4. Espere el mensaje de confirmación.
5. Solo después de eso, vuelva a usar Render.

> **Orden importante:** primero **Enviar cambios a Render** y después el
> respaldo normal. Si hace el respaldo normal primero, la copia de Render
> reemplazaría lo que usted trabajó en 260 durante la caída.

### 7.5. Qué se copia y qué no

Se copian: usuarios y contraseñas, registros de actividades, catálogos,
actividades personales, configuraciones y tickets de la mesa de ayuda.

No se copian: sesiones abiertas, intentos de login y la bitácora de auditoría.
Son datos propios de cada servidor y no hacen falta para operar.

---

## 8. Problemas comunes

| Mensaje o síntoma | Qué hacer |
|---|---|
| `could not find driver` | Activar la extensión `pdo_mysql` en el panel de PHP. |
| `Access denied for user` | La contraseña o el usuario de MySQL no coinciden. Revise `config.local.php`. |
| `Unknown database` | La base de datos no existe. Créela en el panel de 260mb.net. |
| Página en blanco o error 500 | Revise que la versión de PHP sea 7.4 o superior y que estén activas `mbstring` y `zip`. Consulte el registro de errores del hosting. |
| `No se pudo cargar la copia de datos` | Suba de nuevo `datos/datos_iniciales.json` en modo binario. También puede importar `sql/datos_iniciales.sql` con phpMyAdmin. |
| La instalación dice que la base ya está lista | No vuelva a instalar. Si necesita empezar de cero, vacíe la base desde phpMyAdmin y repita. |
| No se puede subir un Excel grande | Ajuste `upload_max_filesize` y `post_max_size` en `.user.ini` o en el panel de PHP. |
| Las fechas salen con otra hora | La zona horaria está configurada en `America/Bogota` dentro de `config.php`. |

## 9. Si prefiere importar con phpMyAdmin

En lugar de usar el instalador con la copia JSON:

1. Cree la base de datos en 260mb.net.
2. Entre a **phpMyAdmin**.
3. Seleccione la base.
4. Importe `sql/datos_iniciales.sql`.
5. Abra `instalar.php` para crear el usuario administrador, **sin** marcar la
   opción de cargar la copia de datos.
6. Borre `instalar.php`.

## 10. Qué incluye la copia

- 1.901 registros activos, con sus ids originales.
- 7 usuarios.
- 89 valores de catálogo.
- 29 actividades personales.
- 30 configuraciones de usuario.
- Actividades reparadas: ya no quedan textos cortados a 200 caracteres.

La copia se generó el 9 de noviembre de 2026. Si la aplicación de Render siguió
recibiendo registros después de esa fecha, vuelva a generar la copia antes de
instalar: use la herramienta `tools/exportar_datos_php.py` del proyecto y luego
repita la instalación en un entorno de prueba antes de publicar.
