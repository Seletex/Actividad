"""
Notificaciones de la mesa de ayuda.

Se usan las mismas credenciales que la version PHP, pero por variables de
entorno para no guardar secretos en el repositorio:

    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    BREVO_API_KEY, BREVO_SENDER, BREVO_SENDER_NAME
    PUBLIC_URL  (opcional, por defecto el sitio principal en Render)

Si una credencial no esta configurada, la funcion no hace nada y devuelve
False. Nunca lanza excepciones hacia la ruta: un fallo de red no puede impedir
que se radique o resuelva un ticket.
"""

import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from config import logger


def _base_url():
    """URL que se usa en los enlaces de las notificaciones.

    Prioridad: PUBLIC_URL (dominio propio o URL fija), luego la URL publica que
    Render asigna a esta misma instancia (RENDER_EXTERNAL_URL) para que la
    segunda instancia enlace a si misma sin configuracion extra.
    """
    return (
        os.environ.get("PUBLIC_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or "https://actividad-0c88.onrender.com"
    ).rstrip("/")


def _recortar(texto, limite):
    texto = "" if texto is None else str(texto)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _telegram_config():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return None
    return {"token": token, "chat_id": chat_id}


def _brevo_config():
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    remitente = os.environ.get("BREVO_SENDER", "").strip()
    if not api_key or not remitente:
        return None
    return {
        "api_key": api_key,
        "remitente": remitente,
        "nombre_rem": os.environ.get("BREVO_SENDER_NAME", "Soporte TI").strip()
        or "Soporte TI",
    }


def _post_json(url, payload, headers, timeout=8):
    datos = json.dumps(payload).encode("utf-8")
    peticion = urllib.request.Request(url, data=datos, method="POST")
    for clave, valor in headers.items():
        peticion.add_header(clave, valor)
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return 200 <= respuesta.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        logger.warning("No se pudo enviar notificación (%s): %s", url, e)
        return False


def enviar_telegram(mensaje):
    """Envia un mensaje HTML al chat configurado de Telegram."""
    cfg = _telegram_config()
    if not cfg:
        return False
    url = "https://api.telegram.org/bot" + cfg["token"] + "/sendMessage"
    return _post_json(
        url,
        {
            "chat_id": cfg["chat_id"],
            "text": mensaje,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        {"Content-Type": "application/json"},
        timeout=6,
    )


def enviar_correo_brevo(destino, nombre, asunto, cuerpo_html):
    """Envia un correo con la API v3 de Brevo."""
    cfg = _brevo_config()
    if not cfg:
        return False
    destino = (destino or "").strip()
    if not destino or "@" not in destino:
        return False
    payload = {
        "sender": {
            "name": cfg["nombre_rem"],
            "email": cfg["remitente"],
        },
        "to": [
            {
                "email": destino,
                "name": (nombre or destino).strip(),
            }
        ],
        "subject": asunto,
        "htmlContent": cuerpo_html,
    }
    return _post_json(
        "https://api.brevo.com/v3/smtp/email",
        payload,
        {
            "accept": "application/json",
            "api-key": cfg["api_key"],
            "content-type": "application/json",
        },
    )


def notificar_ticket_nuevo(ticket):
    """Avisa por Telegram y correo que entro una solicitud nueva."""
    if not ticket:
        return

    icono = "🚨" if ticket.get("prioridad") in ("Urgente", "Alta") else "📩"
    mensaje = (
        f"{icono} <b>NUEVA SOLICITUD DE SOPORTE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>Radicado:</b> <code>{html.escape(str(ticket.get('radicado', '')))}</code>\n"
        f"🏢 <b>Dependencia:</b> {html.escape(str(ticket.get('dependencia', '')))}\n"
        f"👤 <b>Solicitante:</b> {html.escape(str(ticket.get('solicitante', '')))}\n"
        f"⚙️ <b>Tipo:</b> {html.escape(str(ticket.get('tipo_solicitud', '')))}\n"
        f"⚡ <b>Prioridad:</b> {html.escape(str(ticket.get('prioridad', '')))}\n"
    )
    if ticket.get("telefono"):
        mensaje += f"📞 <b>Teléfono:</b> {html.escape(str(ticket.get('telefono')))}\n"
    mensaje += (
        f"📝 <b>Detalle:</b>\n<i>{html.escape(_recortar(ticket.get('descripcion'), 200))}</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f'👉 <a href="{_base_url()}/tickets">Ver y atender en el sistema</a>'
    )
    enviar_telegram(mensaje)

    if ticket.get("correo"):
        _enviar_correo_nuevo(ticket)


def notificar_ticket_resuelto(ticket, tecnico, todos, solucion):
    """Avisa por Telegram y correo que el ticket fue resuelto."""
    if not ticket:
        return

    mensaje = (
        "✅ <b>TICKET SOLUCIONADO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>Radicado:</b> <code>{html.escape(str(ticket.get('radicado', '')))}</code>\n"
        f"🏢 <b>Dependencia:</b> {html.escape(str(ticket.get('dependencia', '')))}\n"
        f"👤 <b>Solicitante:</b> {html.escape(str(ticket.get('solicitante', '')))}\n"
        f"🛠️ <b>Atendido por:</b> {html.escape(', '.join(todos))}\n"
        f"💡 <b>Solución:</b>\n<i>{html.escape(_recortar(solucion, 250))}</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📁 <i>Actividades oficiales creadas e imputadas automáticamente en el informe.</i>"
    )
    enviar_telegram(mensaje)

    if ticket.get("correo"):
        _enviar_correo_resuelto(ticket, solucion, todos)


def _enviar_correo_nuevo(ticket):
    radicado = html.escape(str(ticket.get("radicado", "")))
    solicitante = html.escape(str(ticket.get("solicitante", "")))
    dependencia = html.escape(str(ticket.get("dependencia", "")))
    tipo = html.escape(str(ticket.get("tipo_solicitud", "")))
    prioridad = html.escape(str(ticket.get("prioridad", "")))
    descripcion = html.escape(str(ticket.get("descripcion", ""))).replace("\n", "<br>")
    fecha = html.escape(str(ticket.get("fecha_creacion", "")))
    enlace = _base_url() + "/ticket?radicado=" + urllib.parse.quote(
        str(ticket.get("radicado", ""))
    )
    asunto = f"📋 Radicado {ticket.get('radicado', '')} - Solicitud de Soporte Técnico Recibida"

    cuerpo = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Notificación de Soporte TI</title></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" style="background:#f0f2f5;padding:25px 10px;">
<tr><td align="center">
<table width="100%" style="max-width:620px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0;">
<tr><td style="background:linear-gradient(135deg,#0f2b46 0%,#1e4b75 100%);padding:32px 30px;text-align:center;">
<h1 style="color:#ffffff;margin:0;font-size:24px;">Mesa de Ayuda &amp; Soporte TI</h1>
<p style="color:#cbd5e1;margin:6px 0 0 0;font-size:14px;">Alcaldía de La Ceja - Antioquia</p>
</td></tr>
<tr><td style="padding:35px;">
<p style="font-size:16px;color:#1e293b;">Estimado(a) <strong>{solicitante}</strong>,</p>
<p style="font-size:14px;color:#475569;">Su requerimiento fue registrado exitosamente. Estos son los datos:</p>
<table width="100%" style="background:#f8fafc;border:2px dashed #3b82f6;border-radius:10px;margin-bottom:25px;">
<tr><td style="padding:18px;text-align:center;">
<span style="font-size:11px;color:#64748b;text-transform:uppercase;">Número de Radicado Oficial</span><br>
<span style="font-size:26px;font-weight:800;color:#1e40af;font-family:monospace;">{radicado}</span><br>
<span style="font-size:12px;color:#64748b;">Conserve este código para consultar el avance.</span>
</td></tr></table>
<table width="100%" style="border:1px solid #e2e8f0;border-radius:8px;margin-bottom:25px;border-collapse:separate;overflow:hidden;">
<tr style="background:#f1f5f9;"><td colspan="2" style="padding:10px 16px;font-size:12px;font-weight:700;color:#334155;">📋 Datos del Requerimiento</td></tr>
<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;width:35%;">Dependencia / Área:</td><td style="padding:10px 16px;font-size:13px;color:#0f172a;font-weight:600;">{dependencia}</td></tr>
<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;">Tipo de Solicitud:</td><td style="padding:10px 16px;font-size:13px;color:#0f172a;">{tipo}</td></tr>
<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;">Prioridad:</td><td style="padding:10px 16px;font-size:13px;color:#0f172a;">{prioridad}</td></tr>
<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;">Fecha y Hora:</td><td style="padding:10px 16px;font-size:13px;color:#0f172a;">{fecha}</td></tr>
<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;vertical-align:top;">Descripción:</td><td style="padding:10px 16px;font-size:13px;color:#0f172a;line-height:1.5;">{descripcion}</td></tr>
</table>
<p style="text-align:center;">
<a href="{enlace}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;padding:13px 28px;border-radius:8px;">🔍 Consultar Estado en Línea</a>
</p>
</td></tr>
<tr><td style="background:#f8fafc;padding:22px 30px;text-align:center;color:#94a3b8;font-size:12px;">
<strong style="color:#475569;">Alcaldía de La Ceja - Antioquia</strong><br>
Área de Tecnologías de la Información y las Comunicaciones (TIC)<br>
Canal Oficial: <a href="mailto:sistemasoporte@laceja-antioquia.gov.co" style="color:#2563eb;">sistemasoporte@laceja-antioquia.gov.co</a>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
    enviar_correo_brevo(
        ticket.get("correo"), ticket.get("solicitante"), asunto, cuerpo
    )


def _enviar_correo_resuelto(ticket, solucion, todos):
    radicado = html.escape(str(ticket.get("radicado", "")))
    solicitante = html.escape(str(ticket.get("solicitante", "")))
    dependencia = html.escape(str(ticket.get("dependencia", "")))
    solucion_html = html.escape(str(solucion)).replace("\n", "<br>")
    principal = html.escape(todos[0] if todos else "")
    colaboradores = [html.escape(n) for n in todos[1:]]
    fecha_cierre = html.escape(str(ticket.get("fecha_cierre", "")))
    enlace = _base_url() + "/ticket?radicado=" + urllib.parse.quote(
        str(ticket.get("radicado", ""))
    )
    asunto = f"✅ Ticket {ticket.get('radicado', '')} Resuelto - Mesa de Ayuda Soporte TI"

    fila_colabs = ""
    if colaboradores:
        fila_colabs = (
            '<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;">'
            "Técnico(s) Colaborador(es):</td>"
            '<td style="padding:10px 16px;font-size:13px;color:#0f172a;font-weight:600;">'
            + ", ".join(colaboradores)
            + "</td></tr>"
        )

    cuerpo = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Incidente Solucionado - Soporte TI</title></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" style="background:#f0f2f5;padding:25px 10px;">
<tr><td align="center">
<table width="100%" style="max-width:620px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0;">
<tr><td style="background:linear-gradient(135deg,#065f46 0%,#047857 100%);padding:32px 30px;text-align:center;">
<h1 style="color:#ffffff;margin:0;font-size:24px;">Incidente Solucionado</h1>
<p style="color:#a7f3d0;margin:6px 0 0 0;font-size:14px;">Mesa de Ayuda - Alcaldía de La Ceja</p>
</td></tr>
<tr><td style="padding:35px;">
<p style="font-size:16px;color:#1e293b;">Estimado(a) <strong>{solicitante}</strong>,</p>
<p style="font-size:14px;color:#475569;">Su solicitud con radicado <strong style="font-family:monospace;color:#065f46;">{radicado}</strong> fue <strong>atendida y resuelta con éxito</strong>.</p>
<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-left:5px solid #10b981;border-radius:8px;padding:18px 20px;margin-bottom:24px;">
<span style="font-size:11px;font-weight:700;color:#047857;text-transform:uppercase;">🛠️ Solución Aplicada</span>
<div style="font-size:14px;color:#14532d;line-height:1.6;">{solucion_html}</div>
</div>
<table width="100%" style="border:1px solid #e2e8f0;border-radius:8px;margin-bottom:25px;border-collapse:separate;overflow:hidden;">
<tr style="background:#f8fafc;"><td colspan="2" style="padding:10px 16px;font-size:12px;font-weight:700;color:#334155;">👤 Personal Técnico que Atendió</td></tr>
<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;width:40%;">Técnico Responsable:</td><td style="padding:10px 16px;font-size:13px;color:#0f172a;font-weight:700;">{principal}</td></tr>
{fila_colabs}
<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;">Dependencia Atendida:</td><td style="padding:10px 16px;font-size:13px;color:#0f172a;">{dependencia}</td></tr>
<tr><td style="padding:10px 16px;font-size:13px;color:#64748b;">Fecha y Hora de Cierre:</td><td style="padding:10px 16px;font-size:13px;color:#0f172a;">{fecha_cierre}</td></tr>
</table>
<p style="text-align:center;">
<a href="{enlace}" style="display:inline-block;background:#059669;color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;padding:13px 28px;border-radius:8px;">📄 Ver Constancia Oficial del Caso</a>
</p>
</td></tr>
<tr><td style="background:#f8fafc;padding:22px 30px;text-align:center;color:#94a3b8;font-size:12px;">
<strong style="color:#475569;">Alcaldía de La Ceja - Antioquia</strong><br>
Área de Tecnologías de la Información y las Comunicaciones (TIC)<br>
Contacto: <a href="mailto:sistemasoporte@laceja-antioquia.gov.co" style="color:#059669;">sistemasoporte@laceja-antioquia.gov.co</a>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
    enviar_correo_brevo(
        ticket.get("correo"), ticket.get("solicitante"), asunto, cuerpo
    )
