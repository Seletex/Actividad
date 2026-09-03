
"""
Aplicación Web (Flask) de Gestión de Actividades.
Versión segura y funcional: usa el mismo backend (database.py, html_utils.py, export_service.py)
que la versión LAN (app_web.py), pero con framework Flask, autenticación por contraseña,
protección CSRF, rate limiting y bitácora de auditoría.

Despliegue: gunicorn app:app (ver render.yaml / Procfile)
"""
from flask import Flask, request, redirect, url_for, session, render_template_string, send_file
import os
import json
import html
import re
import secrets
import tempfile
from datetime import datetime
from functools import wraps

from config import logger
from database import (
    cargar_usuarios, guardar_usuarios,
    cargar_actividades, cargar_actividades_globales, guardar_actividades,
    cargar_ubicaciones, guardar_ubicaciones,
    cargar_tipos_solicitud, guardar_tipos_solicitud,
    cargar_medios_solicitud, guardar_medios_solicitud,
    cargar_registros, guardar_registro, eliminar_registro,
    obtener_configuracion_usuario, guardar_configuracion_usuario,
    verificar_credenciales, establecer_contrasena, usuario_tiene_contrasena,
    registrar_auditoria, obtener_bitacora, limpiar_bitacora
)
from web_security import (
    generar_csrf_token, csrf_protect, login_bloqueado,
    registrar_intento_fallido, registrar_intento_exitoso,
    sanitizar, configurar_cookies, seguridad_headers
)
from activity_service import agregar_actividad_personal, eliminar_actividad_personal
from export_service import (
    exportar_registros_filtrados, obtener_estadisticas_exportacion,
    generar_informe_template
)
from html_utils import (
    generar_opciones_actividades, generar_opciones_ubicaciones,
    generar_opciones_tipos_solicitud, generar_opciones_medios_solicitud,
    generar_opciones_usuarios, generar_gestion_usuarios,
    generar_gestion_actividades_globales, generar_gestion_actividades_personales,
    generar_gestion_ubicaciones, generar_gestion_tipos_solicitud,
    generar_gestion_medios_solicitud, generar_tabla_registros_recientes,
    generar_gestion_contrasena, generar_gestion_auditoria
)
from templates import (
    LOGIN_TEMPLATE, MAIN_TEMPLATE, GESTION_TEMPLATE,
    EXPORTAR_TEMPLATE, ESTADISTICAS_TEMPLATE, FORMULARIO_REGISTRO,
    ACCESO_GRANTED_TEMPLATE
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
configurar_cookies(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024


def _ip_cliente():
    return (request.headers.get('X-Forwarded-For', request.remote_addr or '')
            .split(',')[0].strip())


def _inyectar_csrf(html_page):
    """Inyecta el token CSRF real en cada formulario de la página renderizada.
    Reemplaza marcadores __CSRF_TOKEN__ y agrega el campo a formularios sin token."""
    token = generar_csrf_token()
    html_page = html_page.replace('__CSRF_TOKEN__', token)
    # Añadir token a formularios POST que aún no lo tienen
    def _add(m):
        form_tag = m.group(0)
        if 'csrf_token' in form_tag:
            return form_tag
        hidden = f'<input type="hidden" name="csrf_token" value="{token}">'
        return form_tag.rstrip('>') + f'>{hidden}'
    html_page = re.sub(r'<form[^>]*method=["\']POST["\'][^>]*>', _add, html_page, flags=re.IGNORECASE)
    html_page = re.sub(r'<form[^>]*method=["\']post["\'][^>]*>', _add, html_page, flags=re.IGNORECASE)
    return html_page


@app.after_request
def _after(resp):
    return seguridad_headers(resp)


# =============================================================================
# DECORADORES
# =============================================================================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('index', error='Debe iniciar sesión'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('usuario') != 'admin':
            return redirect(url_for('gestion', error='Acceso denegado'))
        return f(*args, **kwargs)
    return wrapper


# =============================================================================
# AUTENTICACIÓN
# =============================================================================

@app.route('/', methods=['GET'])
def index():
    usuario_actual = session.get('usuario')

    if not usuario_actual:
        error_login = ""
        if request.args.get('error'):
            error_login = ('<div class="alert alert-danger">'
                           + html.escape(str(request.args.get('error')))
                           + '</div>')
        page = LOGIN_TEMPLATE.format(error_login=error_login)
        return _inyectar_csrf(page)

    alertas = ""
    if request.args.get('success'):
        alertas = '<div class="alert alert-success alert-dismissible fade show">✅ Registro guardado<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>'
    elif request.args.get('deleted'):
        alertas = '<div class="alert alert-info alert-dismissible fade show">🗑️ Registro eliminado<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>'
    elif request.args.get('error'):
        alertas = ('<div class="alert alert-danger alert-dismissible fade show">❌ '
                   + html.escape(str(request.args.get('error')))
                   + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>')

    df = cargar_registros(None if usuario_actual == 'admin' else usuario_actual)
    tabla_html = generar_tabla_registros_recientes(df, usuario_actual)

    # Sección de registro para usuarios no admin (admin sólo gestiona)
    seccion_registro = ""
    if usuario_actual != 'admin':
        seccion_registro = FORMULARIO_REGISTRO.format(
            opciones_actividades=generar_opciones_actividades(usuario_actual),
            opciones_ubicaciones=generar_opciones_ubicaciones(),
            opciones_tipos=generar_opciones_tipos_solicitud(),
            opciones_medios=generar_opciones_medios_solicitud(),
            fecha_hoy=datetime.now().strftime('%Y-%m-%d')
        )

    importar_html = ""
    if usuario_actual == 'admin':
        importar_html = """
        <div class="card mb-4 border-warning">
          <div class="card-header bg-warning text-dark">
            <h5 class="mb-0"><i class="fas fa-file-import"></i> 📥 Importar Datos / Reportes</h5>
          </div>
          <div class="card-body">
            <p class="small mb-0">Use la sección <b>Exportar</b> para generar reportes e importar datos desde Excel.</p>
          </div>
        </div>
        """

    page = MAIN_TEMPLATE.format(
        usuario_actual=usuario_actual,
        seccion_registro=seccion_registro,
        alertas=alertas,
        tabla_registros=tabla_html,
        importar_html=importar_html
    )
    return _inyectar_csrf(page)


@app.route('/agregar_registro', methods=['POST'])
@login_required
@csrf_protect
def agregar_registro():
    usuario_actual = session.get('usuario')
    ip = _ip_cliente()
    if usuario_actual == 'admin':
        return redirect(url_for('index', error='El administrador no crea registros de actividad'))

    ahora = datetime.now()
    fecha_ingresada = sanitizar(request.form.get('fecha_atencion'), 20)
    if not fecha_ingresada:
        fecha_ingresada = ahora.strftime('%Y-%m-%d')
    fecha_con_hora = f"{fecha_ingresada} {ahora.strftime('%H:%M:%S')}"

    registro = {
        'USUARIO': usuario_actual,
        'FECHA': fecha_con_hora,
        'TIPO DE ACTIVIDAD': sanitizar(request.form.get('actividad'), 200),
        'DEPENDENCIA': sanitizar(request.form.get('ubicacion'), 120),
        'SOLICITANTE': sanitizar(request.form.get('solicitante'), 120),
        'TIPO DE SOLICITUD': sanitizar(request.form.get('tipo_solicitud'), 120),
        'MEDIO DE SOLICITUD': sanitizar(request.form.get('medio_solicitud'), 120),
        'CUMPLIDO': sanitizar(request.form.get('cumplido'), 20) or 'Sí',
        'FECHA ATENCIÓN': fecha_ingresada,
        'DESCRIPCIÓN': sanitizar(request.form.get('descripcion'), 2000),
        'OBSERVACIONES': sanitizar(request.form.get('observaciones'), 1000)
    }

    if guardar_registro(registro):
        return redirect(url_for('index', success=1))
    return redirect(url_for('index', error='Error al guardar'))


@app.route('/login', methods=['POST'])
@csrf_protect
def login():
    ip = _ip_cliente()
    if login_bloqueado(ip):
        registrar_auditoria("?", "LOGIN_BLOQUEADO", "Múltiples intentos fallidos", ip)
        return redirect(url_for('index', error='Demasiados intentos. Espere unos minutos.'))

    usuario = sanitizar(request.form.get('usuario'), 50)
    contrasena = request.form.get('clave', request.form.get('contrasena', ''))

    if not usuario:
        return redirect(url_for('index', error='Ingrese su usuario'))

    ok, motivo = verificar_credenciales(usuario, contrasena)
    if not ok:
        registrar_intento_fallido(ip)
        registrar_auditoria(usuario, "LOGIN_FALLIDO", f"Motivo: {motivo}", ip)
        if motivo == 'usuario_inexistente':
            msg = 'Usuario no encontrado'
        elif motivo == 'sin_contrasena':
            msg = 'Su cuenta aún no tiene contraseña. Solicítela al administrador o configúrela.'
        else:
            msg = 'Contraseña incorrecta'
        return redirect(url_for('index', error=msg))

    # Regenerar sesión para evitar fijación de sesión
    session.clear()
    session['usuario'] = usuario
    session.permanent = True
    generar_csrf_token()
    registrar_intento_exitoso(ip)
    registrar_auditoria(usuario, "LOGIN", "Inicio de sesión", ip)
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    ip = _ip_cliente()
    user = session.get('usuario')
    if user:
        registrar_auditoria(user, "LOGOUT", "Cierre de sesión", ip)
    session.clear()
    return redirect(url_for('index'))


# =============================================================================
# SEGURIDAD DE CUENTA
# =============================================================================

@app.route('/cambiar_contrasena', methods=['POST'])
@login_required
@csrf_protect
def cambiar_contrasena():
    usuario = session.get('usuario')
    ip = _ip_cliente()

    nueva = request.form.get('nueva_contrasena', '')
    confirmar = request.form.get('confirmar_contrasena', '')

    if usuario_tiene_contrasena(usuario):
        actual = request.form.get('contrasena_actual', '')
        if not verificar_credenciales(usuario, actual)[0]:
            registrar_auditoria(usuario, "CAMBIO_CLAVE_RECHAZADO", "Contraseña actual incorrecta", ip)
            return redirect(url_for('gestion', error='La contraseña actual es incorrecta'))

    if nueva != confirmar:
        return redirect(url_for('gestion', error='Las contraseñas no coinciden'))

    ok, msg = establecer_contrasena(usuario, nueva)
    accion = "CONTRASENA_INICIAL" if not usuario_tiene_contrasena(usuario) else "CAMBIO_CONTRASENA"
    registrar_auditoria(usuario, accion, msg, ip)
    return redirect(url_for('gestion', msg=('Contraseña actualizada correctamente' if ok else 'Error al actualizar')))


# =============================================================================
# GESTIÓN
# =============================================================================

@app.route('/gestion')
@login_required
def gestion():
    usuario_actual = session.get('usuario')
    es_admin = usuario_actual == 'admin'

    alertas = ""
    if request.args.get('msg'):
        alertas = ('<div class="alert alert-success alert-dismissible fade show">✅ '
                   + html.escape(str(request.args.get('msg')))
                   + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>')
    elif request.args.get('error'):
        alertas = ('<div class="alert alert-danger alert-dismissible fade show">❌ '
                   + html.escape(str(request.args.get('error')))
                   + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>')

    gestion_actividades = generar_gestion_actividades_globales() if es_admin else ""
    gestion_usuarios = generar_gestion_usuarios(usuario_actual) if es_admin else ""
    gestion_ubicaciones = generar_gestion_ubicaciones() if es_admin else ""
    gestion_tipos = generar_gestion_tipos_solicitud() if es_admin else ""
    gestion_medios = generar_gestion_medios_solicitud() if es_admin else ""
    gestion_personal = generar_gestion_actividades_personales(usuario_actual) if not es_admin else ""

    extra = generar_gestion_contrasena(usuario_actual)
    if es_admin:
        extra += generar_gestion_auditoria()

    contrato_vals = {}
    try:
        cfg = obtener_configuracion_usuario('admin')
        contrato_vals = cfg.get('datos_contrato', {}) if cfg else {}
    except Exception:
        contrato_vals = {}

    page = GESTION_TEMPLATE.format(
        usuario_actual=usuario_actual,
        gestion_actividades=f"{gestion_actividades}{gestion_ubicaciones}{gestion_tipos}{gestion_medios}",
        gestion_usuarios=gestion_usuarios,
        gestion_personal=gestion_personal,
        alertas=alertas,
        datos_nro=contrato_vals.get('nro', ''),
        datos_objeto=contrato_vals.get('objeto', ''),
        datos_nombre=contrato_vals.get('nombre', ''),
        datos_cedula=contrato_vals.get('cedula', ''),
        datos_supervisor=contrato_vals.get('supervisor', '')
    )
    page = page.replace('<!-- EXTRA_GESTION -->', extra)
    return _inyectar_csrf(page)


@app.route('/auditoria')
@login_required
@admin_required
def auditoria():
    usuario_actual = session.get('usuario')
    eventos = obtener_bitacora(500)

    iconos = {
        'LOGIN': '🟢', 'LOGIN_FALLIDO': '🔴', 'LOGIN_BLOQUEADO': '⛔',
        'LOGOUT': '⚪', 'CAMBIO_CONTRASENA': '🔑', 'CONTRASENA_INICIAL': '🔑',
        'CAMBIO_CLAVE_RECHAZADO': '🔒', 'ELIMINAR_REGISTRO': '🗑️',
        'CREAR_USUARIO': '➕', 'ELIMINAR_USUARIO': '➖',
        'CREAR_UBICACION': '📍', 'ELIMINAR_UBICACION': '❌',
        'CONFIG_CONTRATO': '📄', 'LIMPIAR_BITACORA': '🧹',
    }

    filas = ""
    for ev in eventos:
        filas += (
            f"<tr><td class='small text-muted'>{html.escape(str(ev.get('fecha','')))}</td>"
            f"<td>{iconos.get(ev['accion'], '·')} <b>{html.escape(str(ev.get('usuario','')))}</b></td>"
            f"<td>{html.escape(str(ev.get('accion','')))}</td>"
            f"<td class='small'>{html.escape(str(ev.get('detalle','')))}</td>"
            f"<td class='small text-muted'>{html.escape(str(ev.get('ip','')))}</td></tr>"
        )
    if not filas:
        filas = "<tr><td colspan='5' class='text-center text-muted'>No hay eventos registrados</td></tr>"

    alertas = ""
    if request.args.get('msg'):
        alertas = ('<div class="alert alert-success alert-dismissible fade show">✅ '
                   + html.escape(str(request.args.get('msg')))
                   + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>')

    page = ACCESO_GRANTED_TEMPLATE.format(
        alertas=alertas,
        usuario_actual=usuario_actual,
        tabla_auditoria=filas
    )
    return _inyectar_csrf(page)


@app.route('/limpiar_auditoria', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def limpiar_auditoria_route():
    ip = _ip_cliente()
    if limpiar_bitacora():
        registrar_auditoria(session.get('usuario'), "LIMPIAR_BITACORA", "Bitácora limpiada", ip)
        return redirect(url_for('auditoria', msg='Bitácora limpiada'))
    return redirect(url_for('auditoria', msg='No se pudo limpiar'))


# =============================================================================
# ACCIONES ADMINISTRATIVAS (listas y usuarios)
# =============================================================================

@app.route('/agregar_usuario', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def agregar_usuario():
    ip = _ip_cliente()
    nuevo = sanitizar(request.form.get('nuevo_usuario'), 50)
    if nuevo and re.fullmatch(r'[A-Za-z0-9 ._@\-]{1,50}', nuevo):
        data = cargar_usuarios()
        usuarios = data.get("usuarios", [])
        if nuevo not in usuarios and nuevo.lower() != 'admin':
            usuarios.append(nuevo)
            data["usuarios"] = usuarios
            if guardar_usuarios(data):
                registrar_auditoria(session.get('usuario'), "CREAR_USUARIO", f"Nuevo usuario: {nuevo}", ip)
                return redirect(url_for('gestion', msg='Usuario agregado'))
    return redirect(url_for('gestion', error='Error al agregar usuario'))


@app.route('/eliminar_usuario', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def eliminar_usuario():
    ip = _ip_cliente()
    usuario = sanitizar(request.form.get('usuario'), 50)
    if usuario and usuario != 'admin':
        data = cargar_usuarios()
        if usuario in data.get("usuarios", []):
            data["usuarios"].remove(usuario)
            if guardar_usuarios(data):
                registrar_auditoria(session.get('usuario'), "ELIMINAR_USUARIO", f"Usuario eliminado: {usuario}", ip)
                return redirect(url_for('gestion', msg='Usuario eliminado'))
    return redirect(url_for('gestion', error='Error al eliminar usuario'))


@app.route('/guardar_datos_contrato', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def guardar_datos_contrato():
    ip = _ip_cliente()
    datos = {
        'nro': sanitizar(request.form.get('nro'), 100),
        'objeto': sanitizar(request.form.get('objeto'), 500),
        'nombre': sanitizar(request.form.get('nombre'), 150),
        'cedula': sanitizar(request.form.get('cedula'), 50),
        'supervisor': sanitizar(request.form.get('supervisor'), 150)
    }
    try:
        guardar_configuracion_usuario('admin', {'datos_contrato': datos})
        registrar_auditoria(session.get('usuario'), "CONFIG_CONTRATO", "Datos de contrato actualizados", ip)
        return redirect(url_for('gestion', msg='Datos de contrato guardados'))
    except Exception:
        return redirect(url_for('gestion', error='Error al guardar'))


# Rutas de listas globales
@app.route('/agregar_actividad_global', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def agregar_actividad_global():
    ip = _ip_cliente()
    item = sanitizar(request.form.get('nuevo_item'), 200)
    if item:
        act = cargar_actividades_globales()
        if item not in act:
            act.append(item)
            guardar_actividades(act)
            registrar_auditoria(session.get('usuario'), "CREAR_ACTIVIDAD_GLOBAL", f"Actividad: {item}", ip)
    return redirect(url_for('gestion', msg='Actividad agregada'))


@app.route('/eliminar_actividad_global', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def eliminar_actividad_global():
    ip = _ip_cliente()
    item = sanitizar(request.form.get('actividad'), 200)
    if item:
        act = cargar_actividades_globales()
        if item in act:
            act.remove(item)
            guardar_actividades(act)
            registrar_auditoria(session.get('usuario'), "ELIMINAR_ACTIVIDAD_GLOBAL", f"Actividad: {item}", ip)
    return redirect(url_for('gestion', msg='Actividad eliminada'))


@app.route('/agregar_ubicacion', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def agregar_ubicacion():
    ip = _ip_cliente()
    item = sanitizar(request.form.get('nuevo_item'), 120)
    if item:
        lista = cargar_ubicaciones()
        if item not in lista:
            lista.append(item)
            guardar_ubicaciones(lista)
            registrar_auditoria(session.get('usuario'), "CREAR_UBICACION", f"Ubicación: {item}", ip)
    return redirect(url_for('gestion', msg='Ubicación agregada'))


@app.route('/eliminar_ubicacion', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def eliminar_ubicacion():
    ip = _ip_cliente()
    item = sanitizar(request.form.get('ubicacion'), 120)
    if item:
        lista = cargar_ubicaciones()
        if item in lista:
            lista.remove(item)
            guardar_ubicaciones(lista)
            registrar_auditoria(session.get('usuario'), "ELIMINAR_UBICACION", f"Ubicación: {item}", ip)
    return redirect(url_for('gestion', msg='Ubicación eliminada'))


@app.route('/agregar_tipo_solicitud', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def agregar_tipo_solicitud():
    ip = _ip_cliente()
    item = sanitizar(request.form.get('nuevo_item'), 120)
    if item:
        lista = cargar_tipos_solicitud()
        if item not in lista:
            lista.append(item)
            guardar_tipos_solicitud(lista)
            registrar_auditoria(session.get('usuario'), "CREAR_TIPO_SOLICITUD", f"Tipo: {item}", ip)
    return redirect(url_for('gestion', msg='Tipo agregado'))


@app.route('/eliminar_tipo_solicitud', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def eliminar_tipo_solicitud():
    ip = _ip_cliente()
    item = sanitizar(request.form.get('tipo'), 120)
    if item:
        lista = cargar_tipos_solicitud()
        if item in lista:
            lista.remove(item)
            guardar_tipos_solicitud(lista)
            registrar_auditoria(session.get('usuario'), "ELIMINAR_TIPO_SOLICITUD", f"Tipo: {item}", ip)
    return redirect(url_for('gestion', msg='Tipo eliminado'))


@app.route('/agregar_medio_solicitud', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def agregar_medio_solicitud():
    ip = _ip_cliente()
    item = sanitizar(request.form.get('nuevo_item'), 120)
    if item:
        lista = cargar_medios_solicitud()
        if item not in lista:
            lista.append(item)
            guardar_medios_solicitud(lista)
            registrar_auditoria(session.get('usuario'), "CREAR_MEDIO_SOLICITUD", f"Medio: {item}", ip)
    return redirect(url_for('gestion', msg='Medio agregado'))


@app.route('/eliminar_medio_solicitud', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def eliminar_medio_solicitud():
    ip = _ip_cliente()
    item = sanitizar(request.form.get('medio'), 120)
    if item:
        lista = cargar_medios_solicitud()
        if item in lista:
            lista.remove(item)
            guardar_medios_solicitud(lista)
            registrar_auditoria(session.get('usuario'), "ELIMINAR_MEDIO_SOLICITUD", f"Medio: {item}", ip)
    return redirect(url_for('gestion', msg='Medio eliminado'))


# Actividades personales
@app.route('/agregar_actividad_personal', methods=['POST'])
@login_required
@csrf_protect
def agregar_act_personal():
    usuario = session.get('usuario')
    actividad = sanitizar(request.form.get('nueva_actividad'), 200)
    if actividad:
        agregar_actividad_personal(usuario, actividad)
        return redirect(url_for('gestion', msg='Actividad personal agregada'))
    return redirect(url_for('gestion', error='Ingrese una actividad'))


@app.route('/eliminar_actividad_personal', methods=['POST'])
@login_required
@csrf_protect
def eliminar_act_personal():
    usuario = session.get('usuario')
    actividad = sanitizar(request.form.get('actividad'), 200)
    if actividad:
        eliminar_actividad_personal(usuario, actividad)
        return redirect(url_for('gestion', msg='Actividad personal eliminada'))
    return redirect(url_for('gestion', error='Error'))


@app.route('/eliminar_registro_accion', methods=['POST'])
@login_required
@csrf_protect
def eliminar_registro_route():
    ip = _ip_cliente()
    id_registro = request.form.get('id_registro')
    if id_registro:
        try:
            if eliminar_registro(int(id_registro), session.get('usuario')):
                registrar_auditoria(session.get('usuario'), "ELIMINAR_REGISTRO", f"Registro ID {id_registro}", ip)
                return redirect(url_for('index', deleted=1))
        except ValueError:
            pass
    return redirect(url_for('index', error='Error al eliminar'))


# =============================================================================
# ESTADÍSTICAS
# =============================================================================

@app.route('/estadisticas')
@login_required
def estadisticas():
    usuario_actual = session.get('usuario')
    fecha_inicio = request.args.get('fecha_inicio', '').strip() or None
    fecha_fin = request.args.get('fecha_fin', '').strip() or None

    stats = obtener_estadisticas_exportacion(usuario_actual, fecha_inicio, fecha_fin)
    total = stats.get('total_registros', 0)
    fecha_min = stats.get('fecha_min', 'N/A')
    promedio = "0.0"
    if total > 0 and (fecha_inicio or fecha_min != 'N/A'):
        try:
            base_date = datetime.strptime(fecha_inicio, "%Y-%m-%d") if fecha_inicio else datetime.strptime(fecha_min, "%Y-%m-%d")
            end_date = datetime.strptime(fecha_fin, "%Y-%m-%d") if fecha_fin else datetime.now()
            dias = (end_date - base_date).days + 1
            promedio = f"{total / max(1, dias):.1f}"
        except Exception:
            promedio = "N/A"

    tabla_stats = ""
    for u in stats.get('usuarios', []):
        admin_badge = '<span class="badge bg-soft-primary text-primary">Admin</span>' if u['usuario'] == 'admin' else ""
        tabla_stats += f"""
        <tr>
            <td><span class="fw-bold">{html.escape(str(u['usuario']))}</span> {admin_badge}</td>
            <td class="text-center"><span class="badge bg-light text-dark">{u['total']}</span></td>
            <td class="text-center">{html.escape(str(u['cumplimiento']))}</td>
            <td class="small text-muted">{html.escape(str(u['ultima']))}</td>
        </tr>
        """
    if not tabla_stats:
        tabla_stats = "<tr><td colspan='4' class='text-center text-muted'>No hay datos disponibles</td></tr>"

    actividad_stats = stats.get('actividades_stats', [])
    actividad_stats_html = ""
    for a in actividad_stats:
        actividad_stats_html += f"""
        <tr>
            <td class="small" title="{html.escape(str(a['actividad']))}">{html.escape(str(a['actividad'])[:70])}...</td>
            <td class="text-center"><span class="badge bg-light text-dark">{a['total']}</span></td>
            <td class="text-center"><span class="badge bg-success text-white">{a['cumplidos']}</span></td>
            <td class="text-center"><span class="badge bg-secondary">{a['pendientes']}</span></td>
            <td class="text-center">{html.escape(str(a['porcentaje']))}</td>
        </tr>
        """
    if not actividad_stats_html:
        actividad_stats_html = "<tr><td colspan='5' class='text-center text-muted'>No hay datos disponibles</td></tr>"

    page = ESTADISTICAS_TEMPLATE.format(
        usuario_actual=usuario_actual,
        total_registros=total,
        total_tipos_actividad=stats.get('total_tipos_actividad', 0),
        fecha_min=fecha_inicio if fecha_inicio else fecha_min,
        fecha_max=fecha_fin if fecha_fin else stats.get('fecha_max', 'N/A'),
        promedio_diario=promedio,
        data_actividades=json.dumps(stats.get('chart_actividades', {'labels': [], 'data': []})),
        data_cumplimiento=json.dumps(stats.get('chart_cumplimiento', {'labels': [], 'data': []})),
        data_linea=json.dumps(stats.get('chart_linea', {'labels': [], 'data': []})),
        tabla_usuarios_stats=tabla_stats,
        tabla_actividades_stats=actividad_stats_html,
        val_fecha_inicio=fecha_inicio or "",
        val_fecha_fin=fecha_fin or ""
    )
    return page


# =============================================================================
# EXPORTACIÓN
# =============================================================================

@app.route('/exportar', methods=['GET', 'POST'])
@login_required
def exportar():
    usuario_actual = session.get('usuario')

    if request.method == 'GET':
        stats = obtener_estadisticas_exportacion(usuario_actual)
        alertas = ""
        if request.args.get('error'):
            alertas = ('<div class="alert alert-danger">'
                       + html.escape(str(request.args.get('error'))) + '</div>')

        config = obtener_configuracion_usuario(usuario_actual)
        dc = config.get("datos_contrato", {})
        if not any(dc.get(k) for k in ['objeto', 'nro', 'nombre', 'cedula', 'supervisor']):
            try:
                admin_dc = obtener_configuracion_usuario('admin').get("datos_contrato", {})
                if any(admin_dc.get(k) for k in ['objeto', 'nro', 'nombre', 'cedula', 'supervisor']):
                    dc = admin_dc
            except Exception:
                pass

        filtro_usuario_html = ""
        importar_html = ""
        if usuario_actual == "admin":
            filtro_usuario_html = f"""
            <div class="col-md-3">
                <div class="mb-3">
                    <label class="form-label">Filtrar por Usuario</label>
                    <select class="form-select" name="usuario_filtro">
                        <option value="Todos" selected>Todos los usuarios</option>
                        {generar_opciones_usuarios()}
                    </select>
                </div>
            </div>
            """

        personales = cargar_actividades(usuario_actual)
        todas = sorted(set(personales))
        opciones = "\n".join(f'<option value="{a}">{a}</option>' for a in todas)

        page = EXPORTAR_TEMPLATE.format(
            usuario_actual=usuario_actual,
            opciones_actividades=opciones,
            alertas=alertas,
            fecha_min=stats.get('fecha_min', 'N/A'),
            fecha_max=stats.get('fecha_max', 'N/A'),
            total_registros=stats.get('total_registros', 0),
            total_tipos_actividad=stats.get('total_tipos_actividad', 0),
            ultima_exportacion=stats.get('ultima_exportacion', 'Nunca'),
            filtro_usuario_html=filtro_usuario_html,
            importar_html=importar_html,
            val_contrato_objeto=dc.get('objeto', ''),
            val_contrato_nro=dc.get('nro', ''),
            val_contrato_nombre=dc.get('nombre', ''),
            val_contrato_cedula=dc.get('cedula', ''),
            val_contrato_supervisor=dc.get('supervisor', '')
        )
        return _inyectar_csrf(page)

    # POST: generar exportación
    if not _csrf_ok():
        return redirect(url_for('exportar', error='Sesión expirada. Intente nuevamente.'))

    fecha_inicio = request.form.get('fecha_inicio', '').strip() or None
    fecha_fin = request.form.get('fecha_fin', '').strip() or None
    actividad = request.form.get('actividad', '').strip() or None
    formato = request.form.get('formato', 'excel').strip()
    tipo_reporte = request.form.get('tipo_reporte', 'detallado').strip()
    usuario_filtro = request.form.get('usuario_filtro', usuario_actual).strip()

    contrato_data = {
        'objeto': sanitizar(request.form.get('contrato_objeto'), 500),
        'nro': sanitizar(request.form.get('contrato_nro'), 100),
        'nombre': sanitizar(request.form.get('contrato_nombre'), 150),
        'cedula': sanitizar(request.form.get('contrato_cedula'), 50),
        'supervisor': sanitizar(request.form.get('contrato_supervisor'), 150)
    }
    try:
        config = obtener_configuracion_usuario(usuario_actual)
        config["datos_contrato"] = contrato_data
        guardar_configuracion_usuario(usuario_actual, config)
    except Exception:
        pass

    if usuario_actual != "admin":
        usuario_filtro = usuario_actual
    elif usuario_filtro == "Todos":
        usuario_filtro = None

    df, _ = exportar_registros_filtrados(
        fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
        usuario=usuario_filtro, actividad=actividad
    )
    if df.empty:
        return redirect(url_for('exportar', error='No hay datos para exportar'))

    tmp_path = None
    try:
        suffix = '.xlsx' if formato == 'excel' else '.csv'
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)

        if formato == 'excel':
            generado = False
            if tipo_reporte == 'final':
                from export_final_service import generar_informe_final_resumen
                generado = generar_informe_final_resumen(df, tmp_path, contrato_data=contrato_data, usuario=usuario_filtro)
            else:
                generado = generar_informe_template(df, tmp_path, contrato_data=contrato_data)
            if not generado:
                return redirect(url_for('exportar', error='No se pudo generar el archivo Excel'))
            filename = f"Informe_{tipo_reporte}_{usuario_actual}_{datetime.now().strftime('%Y%m%d')}.xlsx"
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            df.to_csv(tmp_path, index=False, encoding='utf-8-sig')
            filename = f"exportacion_{usuario_actual}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            mimetype = 'text/csv; charset=utf-8-sig'

        import io
        with open(tmp_path, 'rb') as f:
            data = io.BytesIO(f.read())
        return send_file(data, as_attachment=True, download_name=filename, mimetype=mimetype)
    except Exception as e:
        logger.error(f"Error exportando: {e}")
        return redirect(url_for('exportar', error='Error al procesar la exportación'))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _csrf_ok():
    token = session.get('csrf_token')
    if not token:
        return False
    form_token = request.form.get('csrf_token', '')
    header_token = request.headers.get('X-CSRFToken', '')
    ok_f = form_token and secrets.compare_digest(token, form_token)
    ok_h = header_token and secrets.compare_digest(token, header_token)
    return bool(ok_f or ok_h)


# =============================================================================
# INICIALIZACIÓN (Render/Gunicorn)
# =============================================================================

def initialize_app():
    try:
        from database import inicializar_usuarios, inicializar_config, inicializar_excel
        with app.app_context():
            inicializar_usuarios()
            inicializar_config()
            inicializar_excel()
        logger.info("Aplicación inicializada correctamente (Usuarios, Config, Excel)")
    except Exception as e:
        logger.error(f"Error durante la inicialización: {e}")


initialize_app()

if __name__ == '__main__':
    print("Iniciando servidor Flask local...")
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
