"""
Plantillas de la mesa de ayuda (portal publico y gestion por tecnicos).

Se construyen con reemplazo de marcadores (no con ``str.format``) para que el
CSS y el JavaScript puedan conservar sus llaves sin escapes.
"""

import html
import json
import re
from datetime import datetime

from templates import _NAVBAR_TEMPLATE, _SHARED_STYLES, _SIDEBAR_TEMPLATE


def _e(valor):
    return html.escape("" if valor is None else str(valor))


DEPENDENCIAS_OFICIALES = [
    "ACCION COMUNAL", "AGRONEGOCIOS", "ALCALDÍA", "ALMACEN MUNICIPAL",
    "ARCHIVO GENERAL", "BIBLIOTECAS", "CAI OBREROS DE CRISTO",
    "CASA DE JUSTICIA", "CASA DE LA MUJER", "CATASTRO", "CENTRO DEL CUIDADO",
    "CENTRO DÍA", "COMISARÍA DE FAMILIA", "COMUNICACIONES", "CONCEJO MUNICIPAL",
    "CONTABILIDAD", "CONTRATACION", "CONTROL DISCIPLINARIO", "CONTROL INTERNO",
    "CORREGIDURIA SAN JOSE", "CULTURA", "DESARROLLO COMUNITARIO",
    "DESARROLLO ECONOMICO", "EDUCACION Y CULTURA", "EDUCACIÓN",
    "EJECUCIONES FISCALES", "FAMILIA", "GAULA", "GESTION HUMANA",
    "GESTIÓN PREDIAL", "GOBIERNO", "HACIENDA", "HOSPITAL DE LA CEJA",
    "IMPUESTOS", "INFRAESTRUCTURA", "INSPECCIÓN DE POLICÍA", "MEDIO AMBIENTE",
    "NOMINA", "OFICINA DE SISTEMAS", "PARQUE EDUCATIVO", "PERSONERÍA",
    "PLANEACIÓN", "PLAZA DE MERCADO", "PRESUPUESTO", "PROTECCION SOCIAL",
    "PROYECCIÓN SOCIAL", "RADIO CAPIRO", "SAIMYR", "SALUD",
    "SECRETARIA PRIVADA", "SEGURIDAD Y SALUD EN EL TRABAJO", "SIJIN", "SISBEN",
    "TEATRO MUNICIPAL", "TESORERIA", "TRÁNSITO Y TRANSPORTE", "UAI",
    "VENTANILLA ÚNICA", "VICTIMAS", "VIVIENDA",
]

TIPOS_SOLICITUD_MESA_AYUDA = [
    "Impresoras (Configuración / No imprime / Tóner)",
    "Escáner / Digitalización de documentos",
    "Hardware / Falla en equipo (No enciende / Se apaga / Pantalla)",
    "Mantenimiento Preventivo / Limpieza física",
    "Revisión de Periféricos (Teclado, Mouse, Monitor, Cables)",
    "Red e Internet (Sin conexión / Caída de red / Wi-Fi)",
    "Punto de Red / Conector RJ45 dañado",
    "Telefonía IP / Configuración de Extensión",
    "Software / Instalación o actualización de programas",
    "Microsoft Office (Word, Excel, Outlook / Activación)",
    "Aplicativos Institucionales (SAIMYR, Catastro, SECOP, etc.)",
    "Antivirus / Detección y limpieza de virus",
    "Correo Institucional (Acceso, configuración o fallas)",
    "Cambio o restablecimiento de contraseña",
    "Asignación o retiro de permisos y usuarios",
    "Acceso al Dominio / Carpetas compartidas en servidor",
    "Apoyo técnico en Sala de Juntas / Eventos / Concejo",
    "Configuración de Video Beam / Proyector / Sonido",
    "Préstamo de equipo portátil para comisión o evento",
    "Consulta / Asesoría y acompañamiento tecnológico",
    "Otros requerimientos de soporte TI",
]


PORTAL_TICKET_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mesa de Ayuda - Solicitudes de Soporte TI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; min-height: 100vh; display: flex; flex-direction: column; }
        .header-mesa { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 35px 0 25px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .card-custom { border: none; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); background: white; }
        .nav-pills .nav-link { border-radius: 8px; padding: 10px 20px; font-weight: 500; color: #495057; }
        .nav-pills .nav-link.active { background-color: #2a5298; color: white; }
        .badge-estado-pendiente { background-color: #ffc107; color: #000; font-size: 0.95rem; }
        .badge-estado-proceso { background-color: #0dcaf0; color: #000; font-size: 0.95rem; }
        .badge-estado-resuelto { background-color: #198754; color: #fff; font-size: 0.95rem; }
        .radicado-box { background: #e8f4fd; border: 2px dashed #2a5298; border-radius: 10px; padding: 20px; text-align: center; }
    </style>
</head>
<body>
<header class="header-mesa">
    <div class="container">
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
            <div>
                <h1 class="h3 mb-1"><i class="fas fa-headset me-2"></i> Mesa de Ayuda TI</h1>
                <p class="mb-0 text-white-50">Portal de Solicitudes y Soporte Técnico</p>
            </div>
            <div>
                <a href="/" class="btn btn-outline-light btn-sm">
                    <i class="fas fa-user-shield me-1"></i> Acceso Técnicos
                </a>
            </div>
        </div>
    </div>
</header>
<main class="container my-4 flex-grow-1">
__CONTENIDO__
</main>
<footer class="bg-white border-top py-3 text-center text-muted small mt-auto">
    <div class="container">
        Sistema de Actividades &amp; Mesa de Ayuda TI &copy; __ANIO__
    </div>
</footer>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""


def _portal_alerta(error):
    if not error:
        return ""
    return (
        '<div class="alert alert-danger alert-dismissible fade show" role="alert">'
        '<i class="fas fa-exclamation-circle me-2"></i> '
        + _e(error)
        + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>'
    )


def _portal_formulario(dependencias, tipos):
    opciones_dep = "".join(
        '<option value="' + _e(d) + '"></option>' for d in dependencias
    )
    opciones_tipo = "".join(
        '<option value="' + _e(t) + '"></option>' for t in tipos
    )
    return """
<div class="row justify-content-center">
  <div class="col-lg-8">
    <div class="card card-custom p-4">
      <h4 class="mb-3 text-primary"><i class="fas fa-file-alt me-2"></i> Formulario de Solicitud</h4>
      <p class="text-muted small mb-4">Complete la información para que el equipo técnico atienda su requerimiento oportunamente.</p>
      <form action="/ticket" method="POST">
        <input type="hidden" name="accion" value="crear_ticket">
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label fw-bold">Ubicación / Dependencia *</label>
            <div class="input-group">
              <span class="input-group-text bg-light"><i class="fas fa-building text-muted"></i></span>
              <input type="text" name="dependencia" list="lista-dependencias" class="form-control" placeholder="Escriba o seleccione su ubicación..." required autocomplete="off" maxlength="150">
            </div>
            <datalist id="lista-dependencias">__OPCIONES_DEP__</datalist>
          </div>
          <div class="col-md-6">
            <label class="form-label fw-bold">Nombre del Solicitante *</label>
            <input type="text" name="solicitante" class="form-control" placeholder="Ej: Carlos Pérez" required maxlength="150">
          </div>
          <div class="col-md-6">
            <label class="form-label fw-bold">Tipo de Solicitud *</label>
            <div class="input-group">
              <span class="input-group-text bg-light"><i class="fas fa-tools text-muted"></i></span>
              <input type="text" name="tipo_solicitud" list="lista-tipos" class="form-control" placeholder="Escriba o seleccione el tipo de soporte..." required autocomplete="off" maxlength="150">
            </div>
            <datalist id="lista-tipos">__OPCIONES_TIPO__</datalist>
          </div>
          <div class="col-md-6">
            <label class="form-label fw-bold">Prioridad</label>
            <select name="prioridad" class="form-select">
              <option value="Baja">Baja (Requerimiento general sin urgencia)</option>
              <option value="Media" selected>Media (Atención estándar)</option>
              <option value="Alta">Alta (Afecta operaciones del área)</option>
              <option value="Urgente">Urgente (Servicio completamente caído)</option>
            </select>
          </div>
          <div class="col-md-6">
            <label class="form-label">Teléfono / Celular / Extensión</label>
            <div class="input-group">
              <span class="input-group-text"><i class="fas fa-phone"></i></span>
              <input type="text" name="telefono" class="form-control" placeholder="Para contacto directo" maxlength="50">
            </div>
          </div>
          <div class="col-md-6">
            <label class="form-label">Correo Electrónico (Opcional)</label>
            <div class="input-group">
              <span class="input-group-text"><i class="fas fa-envelope"></i></span>
              <input type="email" name="correo" class="form-control" placeholder="Para notificaciones" maxlength="150">
            </div>
          </div>
          <div class="col-12">
            <label class="form-label fw-bold">Descripción detallada del problema o necesidad *</label>
            <textarea name="descripcion" class="form-control" rows="4" placeholder="Describa qué está sucediendo, mensaje de error, número de equipo o cualquier detalle útil..." required maxlength="2000"></textarea>
          </div>
          <div class="col-12 text-end mt-4">
            <button type="submit" class="btn btn-primary btn-lg px-4">
              <i class="fas fa-paper-plane me-1"></i> Enviar Solicitud
            </button>
          </div>
        </div>
      </form>
    </div>
  </div>
</div>
""".replace("__OPCIONES_DEP__", opciones_dep).replace(
        "__OPCIONES_TIPO__", opciones_tipo
    )


def _portal_creado(ticket):
    radicado = _e(ticket.get("radicado"))
    return """
<div class="card card-custom p-4 mb-4 text-center">
  <div class="text-success mb-3"><i class="fas fa-check-circle fa-4x"></i></div>
  <h3 class="text-success">¡Solicitud Radicada con Éxito!</h3>
  <p class="text-muted">El equipo de soporte ha sido notificado y atenderá su caso a la brevedad.</p>
  <div class="radicado-box my-3 mx-auto" style="max-width:450px;">
    <span class="text-muted d-block small">SU NÚMERO DE RADICADO ES:</span>
    <h2 class="text-primary mb-1 fw-bold">__RADICADO__</h2>
    <small class="text-muted">Guarde este número para consultar el avance de su solicitud.</small>
  </div>
  <div class="mt-3">
    <a href="/ticket?radicado=__RADICADO_URL__" class="btn btn-primary me-2">
      <i class="fas fa-eye me-1"></i> Ver Estado de mi Solicitud
    </a>
    <a href="/ticket" class="btn btn-outline-secondary">
      <i class="fas fa-plus me-1"></i> Radicar Otra Solicitud
    </a>
  </div>
</div>
""".replace("__RADICADO_URL__", _e(ticket.get("radicado"))).replace(
        "__RADICADO__", radicado
    )


def _portal_consulta(ticket, radicado_buscado):
    estado = str(ticket.get("estado") or "Pendiente")
    clase = "badge-estado-pendiente"
    icono = "clock"
    if estado == "En proceso":
        clase, icono = "badge-estado-proceso", "tools"
    elif estado == "Resuelto":
        clase, icono = "badge-estado-resuelto", "check-circle"

    tecnico = (
        '<span class="badge bg-secondary"><i class="fas fa-user-cog me-1"></i> '
        + _e(ticket.get("tecnico_asignado"))
        + "</span>"
        if ticket.get("tecnico_asignado")
        else '<span class="text-muted fst-italic">Pendiente de asignación</span>'
    )

    solucion = ""
    if estado == "Resuelto":
        colaboradores = ""
        try:
            lista = json.loads(ticket.get("tecnicos_colaboradores") or "[]")
            if isinstance(lista, list) and lista:
                colaboradores = " | Técnicos colaboradores: " + _e(", ".join(lista))
        except Exception:
            colaboradores = ""
        solucion = """
<div class="alert alert-success mt-2 mb-0">
  <h6 class="alert-heading mb-1"><i class="fas fa-check-circle me-1"></i> Solución Brindada:</h6>
  <p class="mb-2">__SOLUCION__</p>
  <small class="text-muted d-block border-top pt-1 mt-1">
    Fecha de cierre: __CIERRE____COLABORADORES__
  </small>
</div>
""".replace("__SOLUCION__", _e(ticket.get("solucion")).replace("\n", "<br>")).replace(
            "__CIERRE__", _e(ticket.get("fecha_cierre"))
        ).replace("__COLABORADORES__", colaboradores)

    return """
<div class="card card-custom p-4">
  <div class="d-flex justify-content-between align-items-center flex-wrap pb-3 mb-3 border-bottom gap-2">
    <div>
      <span class="text-muted small d-block">RADICADO</span>
      <h3 class="text-primary mb-0 fw-bold">__RADICADO__</h3>
    </div>
    <div>
      <span class="badge __CLASE__ p-2 px-3"><i class="fas fa-__ICONO__ me-1"></i> __ESTADO__</span>
    </div>
  </div>
  <div class="row g-3 mb-3">
    <div class="col-sm-6"><small class="text-muted d-block">Dependencia</small><strong>__DEPENDENCIA__</strong></div>
    <div class="col-sm-6"><small class="text-muted d-block">Solicitante</small><strong>__SOLICITANTE__</strong></div>
    <div class="col-sm-6"><small class="text-muted d-block">Tipo de Soporte</small><span>__TIPO__</span></div>
    <div class="col-sm-6"><small class="text-muted d-block">Fecha de Radicación</small><span>__FECHA__</span></div>
    <div class="col-sm-6"><small class="text-muted d-block">Técnico Asignado</small>__TECNICO__</div>
    <div class="col-sm-6"><small class="text-muted d-block">Prioridad</small><span class="badge bg-light text-dark border">__PRIORIDAD__</span></div>
  </div>
  <div class="mb-3">
    <small class="text-muted d-block mb-1">Descripción del requerimiento:</small>
    <div class="p-3 bg-light rounded border">__DESCRIPCION__</div>
  </div>
  __SOLUCION__
</div>
""".replace("__RADICADO__", _e(ticket.get("radicado"))).replace(
        "__CLASE__", clase
    ).replace("__ICONO__", icono).replace("__ESTADO__", _e(estado)).replace(
        "__DEPENDENCIA__", _e(ticket.get("dependencia"))
    ).replace("__SOLICITANTE__", _e(ticket.get("solicitante"))).replace(
        "__TIPO__", _e(ticket.get("tipo_solicitud"))
    ).replace("__FECHA__", _e(ticket.get("fecha_creacion"))).replace(
        "__TECNICO__", tecnico
    ).replace("__PRIORIDAD__", _e(ticket.get("prioridad"))).replace(
        "__DESCRIPCION__",
        _e(ticket.get("descripcion")).replace("\n", "<br>"),
    ).replace("__SOLUCION__", solucion)


def render_portal_tickets(
    dependencias,
    tipos,
    error="",
    ticket_creado=None,
    ticket_consultado=None,
    radicado_buscado="",
    pestana="radicar",
):
    """Construye el portal publico de radicacion y consulta."""
    partes = [_portal_alerta(error)]

    partes.append(
        '<ul class="nav nav-pills mb-4 justify-content-center" role="tablist">'
        '<li class="nav-item"><button class="nav-link '
        + ("active" if pestana == "radicar" else "")
        + '" data-bs-toggle="pill" data-bs-target="#pills-radicar" type="button">'
        '<i class="fas fa-plus-circle me-1"></i> Radicar Solicitud</button></li>'
        '<li class="nav-item"><button class="nav-link '
        + ("active" if pestana == "consultar" else "")
        + '" data-bs-toggle="pill" data-bs-target="#pills-consultar" type="button">'
        '<i class="fas fa-search me-1"></i> Consultar Estado</button></li></ul>'
        '<div class="tab-content">'
        '<div class="tab-pane fade '
        + ("show active" if pestana == "radicar" else "")
        + '" id="pills-radicar">'
    )

    if ticket_creado:
        partes.append(_portal_creado(ticket_creado))
    else:
        partes.append(_portal_formulario(dependencias, tipos))

    partes.append(
        '</div><div class="tab-pane fade '
        + ("show active" if pestana == "consultar" else "")
        + '" id="pills-consultar">'
    )

    partes.append(
        """
<div class="row justify-content-center"><div class="col-lg-8">
  <div class="card card-custom p-4 mb-4">
    <h4 class="mb-3 text-primary"><i class="fas fa-search me-2"></i> Consultar Estado de Solicitud</h4>
    <form action="/ticket" method="GET" class="row g-2 align-items-center">
      <input type="hidden" name="consultar" value="1">
      <div class="col-sm-9">
        <div class="input-group input-group-lg">
          <span class="input-group-text bg-white"><i class="fas fa-ticket-alt text-primary"></i></span>
          <input type="text" name="radicado" class="form-control text-uppercase" placeholder="Ingrese número de radicado (Ej: TK-202611-0042)" value="__RADICADO__" required>
        </div>
      </div>
      <div class="col-sm-3">
        <button type="submit" class="btn btn-primary btn-lg w-100"><i class="fas fa-search me-1"></i> Buscar</button>
      </div>
    </form>
  </div>
  __RESULTADO__
</div></div>
""".replace("__RADICADO__", _e(radicado_buscado)).replace(
            "__RESULTADO__",
            _portal_consulta(ticket_consultado, radicado_buscado)
            if ticket_consultado
            else "",
        )
    )

    partes.append("</div></div>")
    contenido = "\n".join(partes)
    return PORTAL_TICKET_PAGE.replace("__CONTENIDO__", contenido).replace(
        "__ANIO__", str(datetime.now().year)
    )


TICKETS_PAGE = (
    """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mesa de Ayuda - Tickets</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
"""
    + _SHARED_STYLES
    + """
        .ticket-metrica { border-left-width: 4px !important; }
        .descripcion-corta { max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    </style>
</head>
<body>
"""
    + _NAVBAR_TEMPLATE.replace("{icono}", "headset")
    .replace("{titulo}", "Mesa de Ayuda")
    .replace("{usuario_actual}", "__USUARIO__")
    + """
    <div class="container-fluid p-0">
        <div class="row g-0">
            """
    + _SIDEBAR_TEMPLATE.format(
        active_inicio="",
        active_listado="",
        active_gestion="",
        active_estadisticas="",
        active_exportar="",
    )
    + """
            <div class="col-md-10 main-content">
                <div class="container-fluid">
                    __ALERTAS__
                    __CONTENIDO__
                </div>
            </div>
        </div>
    </div>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
)


def _badge_estado(estado):
    if estado == "En proceso":
        return '<span class="badge bg-info text-dark">En proceso</span>'
    if estado == "Resuelto":
        return '<span class="badge bg-success text-white">Resuelto</span>'
    return '<span class="badge bg-warning text-dark">Pendiente</span>'


def _badge_prioridad(prioridad):
    clase = "bg-secondary"
    if prioridad == "Alta":
        clase = "bg-danger text-white"
    elif prioridad == "Urgente":
        clase = "bg-danger bg-opacity-75 text-white"
    elif prioridad == "Media":
        clase = "bg-primary text-white"
    return '<span class="badge ' + clase + '">' + _e(prioridad) + "</span>"


def render_gestion_tickets(
    tickets,
    usuarios,
    usuario_actual,
    actividades,
    filtro="Todos",
    resumen=None,
):
    """Construye la bandeja de tickets para los tecnicos."""
    resumen = resumen or {}
    pendientes = int(resumen.get("Pendiente", 0) or 0)
    en_proceso = int(resumen.get("En proceso", 0) or 0)
    resueltos = int(resumen.get("Resuelto", 0) or 0)

    opciones_filtro = ""
    for valor, texto in (
        ("Todos", "Todos los tickets"),
        ("Pendiente", "Solo Pendientes"),
        ("En proceso", "Solo En Proceso"),
        ("Resuelto", "Solo Resueltos"),
    ):
        opciones_filtro += (
            '<option value="'
            + valor
            + '"'
            + (" selected" if filtro == valor else "")
            + ">"
            + texto
            + "</option>"
        )

    opciones_actividad = "".join(
        '<option value="' + _e(a) + '">' + _e(a) + "</option>" for a in actividades
    )
    checks_colaboradores = "".join(
        '<div class="col-sm-6 col-md-4"><div class="form-check">'
        '<input class="form-check-input" type="checkbox" name="colaboradores" '
        'value="' + _e(u) + '" id="colab___ID___' + _e(u) + '">'
        '<label class="form-check-label" for="colab___ID___' + _e(u) + '">'
        + _e(u)
        + "</label></div></div>"
        for u in usuarios
        if u != usuario_actual
    )

    filas = []
    modales = []
    for ticket in tickets:
        tid = int(ticket.get("id") or 0)
        estado = str(ticket.get("estado") or "Pendiente")
        telefono = str(ticket.get("telefono") or "")
        telefono_digitos = re.sub(r"\D", "", telefono)

        contacto = (
            '<br><a href="https://wa.me/57'
            + telefono_digitos
            + '" target="_blank" rel="noopener" class="text-success small text-decoration-none">'
            '<i class="fab fa-whatsapp me-1"></i>'
            + _e(telefono)
            + "</a>"
            if telefono
            else ""
        )

        tecnico = (
            '<span class="badge bg-light text-dark border">'
            '<i class="fas fa-user-cog me-1"></i>'
            + _e(ticket.get("tecnico_asignado"))
            + "</span>"
            if ticket.get("tecnico_asignado")
            else '<span class="text-muted small fst-italic">Sin asignar</span>'
        )

        if estado == "Pendiente":
            accion = (
                '<form method="POST" action="/ticket_tomar" class="d-inline">'
                '<input type="hidden" name="id" value="' + str(tid) + '">'
                '<button type="submit" class="btn btn-sm btn-outline-primary">'
                '<i class="fas fa-hand-holding me-1"></i> Tomar</button></form>'
            )
        elif estado == "En proceso":
            accion = (
                '<button type="button" class="btn btn-sm btn-success" '
                'data-bs-toggle="modal" data-bs-target="#modalResolver'
                + str(tid)
                + '"><i class="fas fa-check-circle me-1"></i> Resolver</button>'
            )
        else:
            accion = (
                '<button type="button" class="btn btn-sm btn-outline-secondary" '
                'data-bs-toggle="modal" data-bs-target="#modalDetalle'
                + str(tid)
                + '"><i class="fas fa-eye me-1"></i> Detalle</button>'
            )

        filas.append(
            """
<tr>
  <td><strong class="text-primary">__RADICADO__</strong><br><small class="text-muted">__FECHA__</small></td>
  <td><strong>__DEPENDENCIA__</strong><br><span class="text-muted small"><i class="fas fa-user me-1"></i>__SOLICITANTE__</span>__CONTACTO__</td>
  <td><span>__TIPO__</span><br>__PRIORIDAD__</td>
  <td><div class="small text-muted descripcion-corta" title="__TITULO__">__DESCRIPCION__</div></td>
  <td>__ESTADO__</td>
  <td>__TECNICO__</td>
  <td class="text-end">__ACCION__</td>
</tr>
""".replace("__RADICADO__", _e(ticket.get("radicado"))).replace(
                "__FECHA__", _e(str(ticket.get("fecha_creacion") or "")[:16])
            ).replace("__DEPENDENCIA__", _e(ticket.get("dependencia"))).replace(
                "__SOLICITANTE__", _e(ticket.get("solicitante"))
            ).replace("__CONTACTO__", contacto).replace(
                "__TIPO__", _e(ticket.get("tipo_solicitud"))
            ).replace(
                "__PRIORIDAD__", _badge_prioridad(ticket.get("prioridad"))
            ).replace(
                "__TITULO__", _e(ticket.get("descripcion"))
            ).replace(
                "__DESCRIPCION__", _e(ticket.get("descripcion"))
            ).replace(
                "__ESTADO__", _badge_estado(estado)
            ).replace(
                "__TECNICO__", tecnico
            ).replace(
                "__ACCION__", accion
            )
        )

        if estado == "En proceso":
            modales.append(
                """
<div class="modal fade" id="modalResolver__ID__" tabindex="-1">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <form method="POST" action="/ticket_resolver">
        <input type="hidden" name="id" value="__ID__">
        <div class="modal-header bg-success text-white">
          <h5 class="modal-title"><i class="fas fa-check-circle me-2"></i> Resolver Ticket __RADICADO__</h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <div class="p-3 mb-3 bg-light rounded border border-start border-primary border-3">
            <div class="row g-2 small">
              <div class="col-md-6"><span class="text-muted d-block">Ubicación / Dependencia:</span><strong>__DEPENDENCIA__</strong></div>
              <div class="col-md-6"><span class="text-muted d-block">Solicitante:</span><strong>__SOLICITANTE__</strong></div>
              <div class="col-12 mt-2 pt-2 border-top"><span class="text-muted d-block">Requerimiento Solicitado:</span><div class="text-dark fst-italic">"__DESCRIPCION__"</div></div>
            </div>
          </div>
          <div class="row g-3 mb-3">
            <div class="col-md-6">
              <label class="form-label fw-bold">Fecha de Atención / Actividad *</label>
              <input type="date" name="fecha_actividad" class="form-control" value="__HOY__" required>
              <small class="text-muted">Fecha que quedará en el informe oficial.</small>
            </div>
            <div class="col-md-6">
              <label class="form-label fw-bold">Tipo de Actividad Oficial (Informe)</label>
              <select name="tipo_actividad" class="form-select">__ACTIVIDADES__</select>
            </div>
          </div>
          <div class="mb-3">
            <label class="form-label fw-bold">Detalle de la Solución Brindada *</label>
            <textarea name="solucion" class="form-control" rows="3" placeholder="Describa qué se realizó..." required></textarea>
          </div>
          <div class="mb-3">
            <label class="form-label fw-bold d-block"><i class="fas fa-users text-primary me-1"></i> ¿Participaron otros técnicos?</label>
            <div class="p-3 bg-light rounded border">
              <small class="text-muted d-block mb-2">Marque los técnicos que colaboraron para que también se les registre la actividad.</small>
              <div class="row g-2">__COLABORADORES__</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
          <button type="submit" class="btn btn-success"><i class="fas fa-save me-1"></i> Guardar y Generar Actividades</button>
        </div>
      </form>
    </div>
  </div>
</div>
""".replace("__ID__", str(tid)).replace(
                    "__RADICADO__", _e(ticket.get("radicado"))
                ).replace("__DEPENDENCIA__", _e(ticket.get("dependencia"))).replace(
                    "__SOLICITANTE__", _e(ticket.get("solicitante"))
                ).replace(
                    "__DESCRIPCION__",
                    _e(ticket.get("descripcion")).replace("\n", "<br>"),
                ).replace(
                    "__HOY__", datetime.now().strftime("%Y-%m-%d")
                ).replace(
                    "__ACTIVIDADES__", opciones_actividad
                ).replace(
                    "__COLABORADORES__", checks_colaboradores.replace("__ID__", str(tid))
                )
            )

        if estado == "Resuelto":
            colaboradores = ""
            try:
                lista = json.loads(ticket.get("tecnicos_colaboradores") or "[]")
                if isinstance(lista, list) and lista:
                    colaboradores = (
                        "<p><strong>Colaboradores:</strong> "
                        + _e(", ".join(lista))
                        + "</p>"
                    )
            except Exception:
                colaboradores = ""
            modales.append(
                """
<div class="modal fade" id="modalDetalle__ID__" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Detalle del Ticket __RADICADO__</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <p><strong>Dependencia:</strong> __DEPENDENCIA__</p>
        <p><strong>Solicitante:</strong> __SOLICITANTE__</p>
        <p><strong>Fecha Solicitud:</strong> __FECHA_CREACION__</p>
        <p><strong>Fecha Solución:</strong> __FECHA_CIERRE__</p>
        <p><strong>Técnico Principal:</strong> __TECNICO__</p>
        __COLABORADORES__
        <hr>
        <h6>Solución Registrada:</h6>
        <div class="p-3 bg-light rounded border">__SOLUCION__</div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cerrar</button>
      </div>
    </div>
  </div>
</div>
""".replace("__ID__", str(tid)).replace(
                    "__RADICADO__", _e(ticket.get("radicado"))
                ).replace("__DEPENDENCIA__", _e(ticket.get("dependencia"))).replace(
                    "__SOLICITANTE__", _e(ticket.get("solicitante"))
                ).replace(
                    "__FECHA_CREACION__", _e(ticket.get("fecha_creacion"))
                ).replace(
                    "__FECHA_CIERRE__", _e(ticket.get("fecha_cierre"))
                ).replace(
                    "__TECNICO__", _e(ticket.get("tecnico_asignado"))
                ).replace(
                    "__COLABORADORES__", colaboradores
                ).replace(
                    "__SOLUCION__",
                    _e(ticket.get("solucion")).replace("\n", "<br>"),
                )
            )

    tabla = "".join(filas) if filas else (
        '<tr><td colspan="7" class="text-center py-5 text-muted">'
        '<i class="fas fa-inbox fa-3x mb-3 text-secondary opacity-50"></i>'
        '<p class="mb-0">No se encontraron tickets en esta categoría.</p></td></tr>'
    )

    return """
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <div>
    <h2 class="mb-0"><i class="fas fa-headset text-primary me-2"></i> Mesa de Ayuda - Tickets</h2>
    <span class="text-muted small">Recepción de solicitudes y conversión automática a actividades oficiales</span>
  </div>
  <a href="/ticket" target="_blank" rel="noopener" class="btn btn-outline-primary">
    <i class="fas fa-external-link-alt me-1"></i> Abrir Portal Público de Radicación
  </a>
</div>

<div class="row g-3 mb-4">
  <div class="col-md-4"><div class="card border-0 shadow-sm bg-warning bg-opacity-25 ticket-metrica border-warning">
    <div class="card-body d-flex justify-content-between align-items-center">
      <div><span class="text-muted small fw-bold">PENDIENTES POR TOMAR</span><h3 class="mb-0 fw-bold">__PENDIENTES__</h3></div>
      <i class="fas fa-clock fa-2x text-warning"></i>
    </div></div></div>
  <div class="col-md-4"><div class="card border-0 shadow-sm bg-info bg-opacity-25 ticket-metrica border-info">
    <div class="card-body d-flex justify-content-between align-items-center">
      <div><span class="text-muted small fw-bold">EN ATENCIÓN ACTUALMENTE</span><h3 class="mb-0 fw-bold">__PROCESO__</h3></div>
      <i class="fas fa-tools fa-2x text-info"></i>
    </div></div></div>
  <div class="col-md-4"><div class="card border-0 shadow-sm bg-success bg-opacity-25 ticket-metrica border-success">
    <div class="card-body d-flex justify-content-between align-items-center">
      <div><span class="text-muted small fw-bold">RESUELTOS Y CONVERTIDOS</span><h3 class="mb-0 fw-bold">__RESUELTOS__</h3></div>
      <i class="fas fa-check-double fa-2x text-success"></i>
    </div></div></div>
</div>

<div class="card shadow-sm mb-4">
  <div class="card-body py-3">
    <form method="GET" action="/tickets" class="row g-2 align-items-center">
      <div class="col-auto"><label class="form-label mb-0 fw-bold small"><i class="fas fa-filter me-1"></i> Filtrar por estado:</label></div>
      <div class="col-auto"><select name="estado" class="form-select form-select-sm" onchange="this.form.submit()">__FILTRO__</select></div>
    </form>
  </div>
</div>

<div class="card shadow-sm">
  <div class="card-body p-0">
    <div class="table-responsive">
      <table class="table table-hover align-middle mb-0">
        <thead class="table-light"><tr>
          <th style="width:130px;">Radicado</th>
          <th>Dependencia / Solicitante</th>
          <th>Tipo / Prioridad</th>
          <th>Descripción</th>
          <th>Estado</th>
          <th>Técnico</th>
          <th class="text-end" style="width:160px;">Acciones</th>
        </tr></thead>
        <tbody>__TABLA__</tbody>
      </table>
    </div>
  </div>
</div>
__MODALES__
""".replace("__PENDIENTES__", str(pendientes)).replace(
        "__PROCESO__", str(en_proceso)
    ).replace("__RESUELTOS__", str(resueltos)).replace(
        "__FILTRO__", opciones_filtro
    ).replace(
        "__TABLA__", tabla
    ).replace(
        "__MODALES__", "".join(modales)
    )
