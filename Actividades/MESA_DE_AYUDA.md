# Mesa de ayuda publicada en Render (dos servicios sincronizados)

Esta guía deja la **mesa de ayuda completa** funcionando en Render junto con la
app de actividades, compartiendo la **misma base de datos Neon** y los **mismos
usuarios**.

La misma aplicación se publica **dos veces**:

| Servicio | Para qué sirve |
|----------|----------------|
| `actividades-app` (el que ya existe) | Uso normal: actividades + mesa de ayuda |
| `mesa-ayuda-app` (nuevo) | Respaldo: si el primero falla, se abre esta URL y todo sigue igual |

Los dos leen y escriben en la misma base, así que un ticket radicado en uno se
ve en el otro, y una actividad resuelta en el respaldo aparece en el informe del
primero.

---

## Antes de empezar: dos advertencias importantes

1. **No use la base PostgreSQL gratuita de Render.** La base real es la de
   **Neon** (plan gratuito que no caduca). Todos los servicios deben apuntar a
   la misma `DATABASE_URL` de Neon.
2. **Horas gratuitas de Render:** el plan gratuito da **750 horas al mes por
   cuenta, compartidas entre todos los servicios**. Un solo servicio encendido
   todo el mes ya consume casi todas. Por eso:
   - Los dos servicios se **duermen solos** a los 15 minutos sin visitas.
   - Use normalmente el servicio principal y abra el respaldo **solo cuando lo
     necesite**. No deje las dos pestañas abiertas todo el día.
   - Si se agotan las horas, Render suspende los servicios gratuitos hasta el
     primer día del mes siguiente.

---

## Paso 1. Aplicar el cambio en el servicio que ya existe

El código nuevo ya está en GitHub (commit `e28b62a`).

1. Entre a [render.com](https://render.com) y abra el servicio actual
   (`https://actividad-0c88.onrender.com`).
2. Pulse **Manual Deploy** → **Deploy latest commit**.
3. Espere a que termine (unos 2 a 5 minutos).
4. Abra en el navegador:

   ```
   https://actividad-0c88.onrender.com/salud
   ```

   Debe responder algo parecido a:

   ```json
   {"servicio":"ok","base_datos":"ok","registros":1903,"version":"e28b62a"}
   ```

   Si `version` todavía no aparece, el despliegue no ha terminado: espere y
   recargue.

Con esto ya queda disponible el portal público:

```
https://actividad-0c88.onrender.com/ticket
```

---

## Paso 2. Crear el segundo servicio (respaldo)

1. En Render pulse **New +** → **Web Service**.
2. Elija el **mismo repositorio** de GitHub (`Seletex/Actividad`).
3. Complete el formulario así:

   | Campo | Valor |
   |-------|-------|
   | **Name** | `mesa-ayuda-app` |
   | **Language / Runtime** | `Python 3` |
   | **Branch** | `main` |
   | **Root Directory** | `Actividades` |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `gunicorn app:app --config gunicorn_config.py` |
   | **Instance Type** | `Free` |
   | **Auto-Deploy** | `Yes` (para que se actualice con cada cambio) |
   | **Health Check Path** | `/salud` |

4. Más abajo, en **Environment Variables**, agregue las variables del paso 3.
5. Pulse **Create Web Service** y espere el primer despliegue.

> Si prefiere usar el archivo `render.yaml`, también está listo para crear las
> dos instancias como **Blueprint**. La vía manual de arriba es la más segura
> para no tocar el servicio que ya está funcionando.

---

## Paso 3. Variables de entorno del segundo servicio

Agregue exactamente estas variables en **Environment** del servicio
`mesa-ayuda-app`:

| Variable | Valor |
|----------|-------|
| `DATABASE_URL` | La **misma** cadena de conexión de Neon que usa el servicio principal. |
| `FLASK_SECRET_KEY` | La **misma** clave que usa el servicio principal. |
| `PYTHON_VERSION` | `3.11.0` |
| `SESSION_COOKIE_SECURE` | `true` |
| `TRUST_PROXY` | `true` |
| `TELEGRAM_TOKEN` | Token del bot de Telegram. |
| `TELEGRAM_CHAT_ID` | Chat o grupo que recibe los avisos. |
| `BREVO_API_KEY` | Clave de Brevo para enviar correos. |
| `BREVO_SENDER` | Correo remitente verificado en Brevo. |
| `BREVO_SENDER_NAME` | `Soporte TI` |

**No configure `PUBLIC_URL` en el segundo servicio.** Así la app usa
automáticamente la URL de ese servicio en los enlaces de Telegram y correo.

### Dónde copiar los valores

- `DATABASE_URL` y `FLASK_SECRET_KEY`: abra el servicio principal en Render →
  **Environment** → muestre/copie el valor. Son datos privados: no los pegue en
  GitHub, correos ni capturas.
- Notificaciones: abra en su equipo el archivo
  `php/config.local.php` y use esta equivalencia:

  | En `config.local.php` | En Render |
  |-----------------------|-----------|
  | `telegram` → `token` | `TELEGRAM_TOKEN` |
  | `telegram` → `chat_id` | `TELEGRAM_CHAT_ID` |
  | `brevo` → `api_key` | `BREVO_API_KEY` |
  | `brevo` → `remitente` | `BREVO_SENDER` |
  | `brevo` → `nombre_rem` | `BREVO_SENDER_NAME` |

  Si deja alguna vacía, la app **no falla**: simplemente no envía ese aviso.

Después de guardar las variables, Render reinicia el servicio solo.

---

## Paso 4. Verificar que las dos quedaron sincronizadas

Anote la URL del segundo servicio (Render la muestra arriba, se parece a
`https://mesa-ayuda-app-xxxx.onrender.com`).

1. **Salud de las dos:**

   ```
   https://actividad-0c88.onrender.com/salud
   https://mesa-ayuda-app-xxxx.onrender.com/salud
   ```

   Las dos deben decir `"servicio":"ok"` y `"base_datos":"ok"`.

2. **Portal público de las dos:**

   ```
   https://actividad-0c88.onrender.com/ticket
   https://mesa-ayuda-app-xxxx.onrender.com/ticket
   ```

   La primera visita del día puede tardar cerca de un minuto (el servicio está
   despertando).

3. **Prueba de sincronización (haga esta prueba una sola vez y luego bórrela):**
   1. Radique un ticket de prueba en el portal del servicio principal. Guarde el
      radicado `TK-...`.
   2. Abra el portal del segundo servicio y consulte ese mismo radicado. Debe
      aparecer.
   3. Entre como técnico al segundo servicio, tome el ticket, resuélvalo y
      marque un colaborador.
   4. Abra el servicio principal → **Listado** (o el informe) y confirme que
      aparecen las actividades de los dos técnicos con medio de solicitud
      **Mesa de Ayuda Web**.

   Así queda demostrado que, si uno falla, el otro puede asumir la carga sin
   perder información.

---

## Paso 5. Respaldo

- Respaldo local del proyecto:
  `C:\Users\apoyosistemas\Documents\Documentos\Respaldo`
- La base de datos no se copia a Render: sigue en Neon.
- Antes de cualquier cambio grande, exporte el informe desde la app y guarde
  una copia del ZIP de respaldo.

---

## Si algo no funciona

| Síntoma | Qué revisar |
|---------|-------------|
| La página tarda ~1 minuto | Es normal en el plan gratuito: el servicio estaba dormido y se está despertando. |
| `/salud` dice `"base_datos":"error"` | La `DATABASE_URL` está mal copiada o le falta `?sslmode=require&channel_binding=require`. |
| El segundo servicio no arranca | Debe tener `FLASK_SECRET_KEY`; sin ella la app se niega a iniciar cuando hay `DATABASE_URL`. |
| No llegan avisos de Telegram o correo | Revise las variables `TELEGRAM_*` / `BREVO_*` y los logs del servicio en Render. |
| Un ticket no aparece en el otro servicio | Confirme que los dos usan **la misma** `DATABASE_URL` de Neon. |
| Se agotaron las horas gratuitas | Render suspende los servicios hasta el día 1 del mes siguiente. Use solo el principal y el respaldo cuando haga falta. |
