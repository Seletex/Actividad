
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
    cargar_registros, guardar_registro, actualizar_registro, eliminar_registro,
    importar_desde_excel,
    obtener_configuracion_usuario, guardar_configuracion_usuario,
    verificar_credenciales, establecer_contrasena, usuario_tiene_contrasena,
    usuario_debe_cambiar_contrasena, marcar_debe_cambiar_contrasena,
    registrar_auditoria, obtener_bitacora, limpiar_bitacora
)
from web_security import (
    generar_csrf_token, csrf_protect, login_bloqueado,
    registrar_intento_fallido, registrar_intento_exitoso,
    sanitizar, configurar_cookies, seguridad_headers
)
from activity_service import agregar_actividad_personal, eliminar_actividad_personal
from admin_bootstrap import aplicar_password_admin_inicial
from excel_import_service import reemplazar_registros_desde_excel
from user_data_service import sincronizar_datos_usuarios
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
    generar_tabla_actividades_completa, generar_opciones_con_seleccion,
    generar_gestion_actividades_personales_por_usuario,
    generar_gestion_contrasena, generar_gestion_auditoria
)
from templates import (
    LOGIN_TEMPLATE, MAIN_TEMPLATE, GESTION_TEMPLATE, LISTADO_TEMPLATE,
    EXPORTAR_TEMPLATE, ESTADISTICAS_TEMPLATE, FORMULARIO_REGISTRO,
    EDIT_REGISTRO_TEMPLATE, ACCESO_GRANTED_TEMPLATE, CAMBIAR_CONTRASENA_TEMPLATE
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


def cambio_requerido(f):
    """Bloquea las rutas hasta que el usuario cambie su contraseña (primer acceso)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('debe_cambiar'):
            return redirect(url_for('cambiar_contrasena_pagina'))
        return f(*args, **kwargs)
    return wrapper


# =============================================================================
# AUTENTICACIÓN
# =============================================================================

@app.route('/', methods=['GET'])
@cambio_requerido
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

    importar_html = _html_importacion(usuario_actual)

    page = MAIN_TEMPLATE.format(
        usuario_actual=usuario_actual,
        seccion_registro=seccion_registro,
        alertas=alertas,
        tabla_registros=tabla_html,
        importar_html=importar_html
    )
    return _inyectar_csrf(page)


def _alertas_listado():
    """Construye los mensajes de resultado de las rutas de listado."""
    success = request.args.get('success', '')
    if success.startswith('importados_'):
        try:
            total = max(0, int(success.split('_', 1)[1]))
        except (TypeError, ValueError):
            total = 0
        mensaje = (
            f'Importación completada: {total} registro(s) nuevo(s) '
            'agregados a PostgreSQL.'
        )
    elif success.startswith('reemplazados_'):
        try:
            total = max(0, int(success.split('_', 1)[1]))
        except (TypeError, ValueError):
            total = 0
        mensaje = (
            f'Reemplazo completado: la tabla quedó con {total} registro(s). '
            'Se creó un respaldo antes de reemplazar.'
        )
    elif success:
        mensaje = 'Registro actualizado correctamente'
    else:
        mensaje = ''

    if mensaje:
        return (
            '<div class="alert alert-success alert-dismissible fade show">✅ '
            + html.escape(mensaje)
            + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>'
            '</div>'
        )
    if request.args.get('error'):
        return (
            '<div class="alert alert-danger alert-dismissible fade show">❌ '
            + html.escape(str(request.args['error']))
            + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>'
            '</div>'
        )
    return ""


def _opciones_con_valor_actual(items, valor_actual):
    """Genera opciones y conserva el valor aunque ya no esté en el catálogo."""
    opciones = list(items or [])
    if valor_actual and valor_actual not in opciones:
        opciones.append(valor_actual)
    return generar_opciones_con_seleccion(opciones, valor_actual)


def _fecha_valida(valor):
    """Normaliza una fecha de formulario a YYYY-MM-DD."""
    valor = sanitizar(valor or "", 10)
    if not valor:
        return ""
    try:
        return datetime.strptime(valor, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _html_importacion(usuario_actual):
    """Muestra el formulario de carga de Excel únicamente al administrador."""
    if usuario_actual != "admin":
        return ""
    return """
    <div class="card mb-4 border-warning">
        <div class="card-header bg-warning text-dark">
            <h5 class="mb-0"><i class="fas fa-file-import"></i> Importar registros desde Excel</h5>
        </div>
        <div class="card-body">
            <form method="POST" action="/importar_excel" enctype="multipart/form-data">
                <input type="hidden" name="csrf_token" value="__CSRF_TOKEN__">
                <div class="row g-3 align-items-end">
                    <div class="col-md-8">
                        <label class="form-label">Archivo .xlsx</label>
                        <input type="file" name="archivo" class="form-control" accept=".xlsx" required>
                        <div class="form-text">
                            Solo se agregan registros que no existan. No se eliminan datos actuales.
                        </div>
                    </div>
                    <div class="col-md-4">
                        <button type="submit" class="btn btn-warning w-100">
                            <i class="fas fa-upload"></i> Importar a PostgreSQL
                        </button>
                    </div>
                </div>
            </form>
        </div>
    </div>

    <div class="card mb-4 border-danger">
        <div class="card-header bg-danger text-white">
            <h5 class="mb-0"><i class="fas fa-database"></i> Reemplazar todos los registros</h5>
        </div>
        <div class="card-body">
            <p class="small text-danger">
                Esta opción crea un respaldo y luego deja la tabla exactamente con
                los registros del archivo. Úsela solo con el Excel de migración validado.
            </p>
            <form method="POST" action="/reemplazar_registros" enctype="multipart/form-data">
                <input type="hidden" name="csrf_token" value="__CSRF_TOKEN__">
                <input type="hidden" name="confirmacion" value="REEMPLAZAR_DATOS">
                <div class="row g-3 align-items-end">
                    <div class="col-md-8">
                        <label class="form-label">Archivo .xlsx de migración</label>
                        <input type="file" name="archivo" class="form-control" accept=".xlsx" required>
                    </div>
                    <div class="col-md-4">
                        <button type="submit" class="btn btn-danger w-100"
                                onclick="return confirm('Se respaldarán los datos actuales y se reemplazarán por los del archivo. ¿Continuar?')">
                            <i class="fas fa-exchange-alt"></i> Respaldar y reemplazar
                        </button>
                    </div>
                </div>
            </form>
        </div>
    </div>

    <div class="card mb-4 border-info">
        <div class="card-header bg-info text-white">
            <h5 class="mb-0"><i class="fas fa-users-cog"></i> Sincronizar usuarios y configuraciones</h5>
        </div>
        <div class="card-body">
            <p class="small mb-3">
                Carga usuarios, actividades personales y datos de contrato desde
                <code>usuarios.json</code>. Puedes seleccionar un JSON migrado más completo.
                Las contraseñas existentes no se modifican.
            </p>
            <form method="POST" action="/sincronizar_usuarios" enctype="multipart/form-data">
                <input type="hidden" name="csrf_token" value="__CSRF_TOKEN__">
                <input type="file" name="archivo" class="form-control mb-2" accept=".json">
                <button type="submit" class="btn btn-info">
                    <i class="fas fa-sync-alt"></i> Sincronizar datos de usuarios
                </button>
            </form>
        </div>
    </div>
    """


@app.route('/listado', methods=['GET'])
@login_required
@cambio_requerido
def listado():
    """Muestra el historial completo de actividades del usuario."""
    usuario_actual = session.get('usuario')
    fecha_inicio = _fecha_valida(request.args.get('fecha_inicio', ''))
    fecha_fin = _fecha_valida(request.args.get('fecha_fin', ''))
    estado = request.args.get('estado', 'Todos').strip()
    if estado not in ('Todos', 'Sí', 'No'):
        estado = 'Todos'

    df = cargar_registros(None if usuario_actual == 'admin' else usuario_actual)

    if not df.empty:
        columna_fecha = None
        if 'FECHA ATENCIÓN' in df.columns:
            columna_fecha = df['FECHA ATENCIÓN']
        elif 'FECHA' in df.columns:
            columna_fecha = df['FECHA']

        if columna_fecha is not None:
            fechas = columna_fecha.fillna('').astype(str).str.slice(0, 10)
            if fecha_inicio:
                df = df[fechas >= fecha_inicio]
                fechas = fechas.loc[df.index]
            if fecha_fin:
                df = df[fechas <= fecha_fin]

        if estado != 'Todos' and 'CUMPLIDO' in df.columns:
            df = df[df['CUMPLIDO'].fillna('').astype(str) == estado]

    tabla_html = generar_tabla_actividades_completa(df, usuario_actual)
    page = LISTADO_TEMPLATE.format(
        usuario_actual=usuario_actual,
        alertas=_alertas_listado(),
        tabla_registros=tabla_html,
        val_fecha_inicio=fecha_inicio,
        val_fecha_fin=fecha_fin,
        sel_todos='selected' if estado == 'Todos' else '',
        sel_si='selected' if estado == 'Sí' else '',
        sel_no='selected' if estado == 'No' else '',
        importar_html=_html_importacion(usuario_actual),
    )
    return _inyectar_csrf(page)


@app.route('/editar_registro', methods=['GET'])
@login_required
@cambio_requerido
def editar_registro():
    """Muestra el formulario de edición de un registro."""
    usuario_actual = session.get('usuario')
    id_registro = request.args.get('id_registro', '').strip()
    if not id_registro.isdigit():
        return redirect(url_for('listado', error='Identificador de registro inválido'))

    df = cargar_registros(None if usuario_actual == 'admin' else usuario_actual)
    if df.empty or 'ID' not in df.columns:
        return redirect(url_for('listado', error='Registro no encontrado'))

    identificadores = df['ID'].fillna('').astype(str).str.replace(
        r'\.0$', '', regex=True
    )
    coincidencias = df[identificadores == id_registro]
    if coincidencias.empty:
        return redirect(url_for('listado', error='Registro no encontrado'))

    registro = coincidencias.iloc[0]
    actividad = str(registro.get('TIPO DE ACTIVIDAD', '') or '')
    ubicacion = str(registro.get('DEPENDENCIA', '') or '')
    tipo_solicitud = str(registro.get('TIPO DE SOLICITUD', '') or '')
    medio_solicitud = str(registro.get('MEDIO DE SOLICITUD', '') or '')
    fecha_atencion = str(registro.get('FECHA ATENCIÓN', '') or '')[:10]
    cumplido = str(registro.get('CUMPLIDO', '') or '')

    page = EDIT_REGISTRO_TEMPLATE.format(
        usuario_actual=usuario_actual,
        id_reg=id_registro,
        opciones_actividades=_opciones_con_valor_actual(
            cargar_actividades(usuario_actual), actividad
        ),
        opciones_ubicaciones=_opciones_con_valor_actual(
            cargar_ubicaciones(), ubicacion
        ),
        opciones_tipos=_opciones_con_valor_actual(
            cargar_tipos_solicitud(), tipo_solicitud
        ),
        opciones_medios=_opciones_con_valor_actual(
            cargar_medios_solicitud(), medio_solicitud
        ),
        val_solicitante=html.escape(
            str(registro.get('SOLICITANTE', '') or '')
        ),
        sel_cumplido_si='selected' if cumplido == 'Sí' else '',
        sel_cumplido_no='selected' if cumplido == 'No' else '',
        val_fecha_atencion=fecha_atencion,
        val_observaciones=html.escape(
            str(registro.get('OBSERVACIONES', '') or '')
        ),
    )
    return _inyectar_csrf(page)


@app.route('/actualizar_registro_accion', methods=['POST'])
@login_required
@cambio_requerido
@csrf_protect
def actualizar_registro_accion():
    """Guarda los cambios enviados desde la edición de un registro."""
    usuario_actual = session.get('usuario')
    ip = _ip_cliente()
    id_registro = request.form.get('id_registro', '').strip()
    if not id_registro.isdigit():
        return redirect(url_for('listado', error='Identificador de registro inválido'))

    cumplido = sanitizar(request.form.get('cumplido', 'No'), 20)
    if cumplido not in ('Sí', 'No'):
        return redirect(url_for('listado', error='Estado de cumplimiento inválido'))

    fecha_atencion = _fecha_valida(request.form.get('fecha_atencion', ''))

    datos = {
        'TIPO DE ACTIVIDAD': sanitizar(request.form.get('actividad'), 200),
        'DEPENDENCIA': sanitizar(request.form.get('ubicacion'), 120),
        'SOLICITANTE': sanitizar(request.form.get('solicitante'), 120),
        'TIPO DE SOLICITUD': sanitizar(request.form.get('tipo_solicitud'), 120),
        'MEDIO DE SOLICITUD': sanitizar(request.form.get('medio_solicitud'), 120),
        'CUMPLIDO': cumplido,
        'FECHA ATENCIÓN': fecha_atencion,
        'OBSERVACIONES': sanitizar(request.form.get('observaciones'), 1000),
    }

    if actualizar_registro(int(id_registro), datos, usuario_actual):
        registrar_auditoria(
            usuario_actual,
            "ACTUALIZAR_REGISTRO",
            f"Registro ID {id_registro}",
            ip,
        )
        return redirect(url_for('listado', success=1))

    return redirect(url_for('listado', error='No se pudo actualizar el registro'))


@app.route('/importar_excel', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def importar_excel():
    """Importa un archivo Excel enviado por el administrador."""
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        return redirect(url_for('listado', error='Seleccione un archivo Excel'))

    nombre = archivo.filename.lower()
    if not nombre.endswith('.xlsx'):
        return redirect(url_for('listado', error='El archivo debe tener extensión .xlsx'))

    ruta_temporal = None
    try:
        descriptor, ruta_temporal = tempfile.mkstemp(suffix='.xlsx')
        os.close(descriptor)
        archivo.save(ruta_temporal)

        if os.path.getsize(ruta_temporal) == 0:
            return redirect(url_for('listado', error='El archivo Excel está vacío'))

        insertados = importar_desde_excel(ruta_temporal)
        registrar_auditoria(
            session.get('usuario'),
            "IMPORTAR_EXCEL",
            f"Registros agregados: {insertados}",
            _ip_cliente(),
        )
        return redirect(url_for('listado', success=f'importados_{insertados}'))
    except Exception:
        logger.exception("Error importando archivo Excel")
        return redirect(url_for('listado', error='No se pudo importar el archivo Excel'))
    finally:
        if ruta_temporal and os.path.exists(ruta_temporal):
            try:
                os.remove(ruta_temporal)
            except Exception:
                pass


@app.route('/reemplazar_registros', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def reemplazar_registros():
    """Reemplaza la tabla de registros con un Excel, creando un respaldo."""
    if request.form.get('confirmacion') != 'REEMPLAZAR_DATOS':
        return redirect(url_for('listado', error='Debe confirmar el reemplazo de datos'))

    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        return redirect(url_for('listado', error='Seleccione un archivo Excel'))
    if not archivo.filename.lower().endswith('.xlsx'):
        return redirect(url_for('listado', error='El archivo debe tener extensión .xlsx'))

    ruta_temporal = None
    try:
        descriptor, ruta_temporal = tempfile.mkstemp(suffix='.xlsx')
        os.close(descriptor)
        archivo.save(ruta_temporal)
        resultado = reemplazar_registros_desde_excel(ruta_temporal)
        registrar_auditoria(
            session.get('usuario'),
            "REEMPLAZAR_REGISTROS",
            (
                f"Total reemplazado: {resultado['total']}; "
                f"respaldo: {resultado['respaldo']}"
            ),
            _ip_cliente(),
        )
        return redirect(
            url_for('listado', success=f"reemplazados_{resultado['total']}")
        )
    except ValueError as exc:
        logger.warning("Archivo de reemplazo inválido: %s", exc)
        return redirect(url_for('listado', error=str(exc)))
    except Exception:
        logger.exception("Error reemplazando registros desde Excel")
        return redirect(url_for('listado', error='No se pudo reemplazar los registros'))
    finally:
        if ruta_temporal and os.path.exists(ruta_temporal):
            try:
                os.remove(ruta_temporal)
            except Exception:
                pass


@app.route('/sincronizar_usuarios', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def sincronizar_usuarios():
    """Sincroniza usuarios y configuraciones desde usuarios.json."""
    ruta_temporal = None
    try:
        archivo = request.files.get('archivo')
        if archivo and archivo.filename:
            if not archivo.filename.lower().endswith('.json'):
                return redirect(url_for('gestion', error='El archivo debe ser un JSON .json'))
            descriptor, ruta_temporal = tempfile.mkstemp(suffix='.json')
            os.close(descriptor)
            archivo.save(ruta_temporal)

        resultado = sincronizar_datos_usuarios(ruta_temporal)
        resumen = resultado["resumen"]
        registrar_auditoria(
            session.get('usuario'),
            "SINCRONIZAR_USUARIOS",
            (
                f"Usuarios nuevos: {resumen['usuarios_nuevos']}; "
                f"actividades agregadas: {resumen['actividades']}; "
                f"actividades duplicadas eliminadas: {resumen['actividades_eliminadas']}; "
                f"configuraciones: {resumen['configuraciones']}; "
                f"listas: {resumen['listas']}"
            ),
            _ip_cliente(),
        )
        return redirect(url_for('gestion', msg='Usuarios y configuraciones sincronizados'))
    except FileNotFoundError:
        logger.exception("No se encontró usuarios.json")
        return redirect(url_for('gestion', error='No se encontró usuarios.json en el servidor'))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("JSON de usuarios inválido: %s", exc)
        return redirect(url_for('gestion', error='El archivo JSON de usuarios no es válido'))
    except Exception:
        logger.exception("Error sincronizando datos de usuarios")
        return redirect(url_for('gestion', error='No se pudieron sincronizar los usuarios'))
    finally:
        if ruta_temporal and os.path.exists(ruta_temporal):
            try:
                os.remove(ruta_temporal)
            except Exception:
                pass


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

    ok, info = verificar_credenciales(usuario, contrasena)
    if not ok:
        registrar_intento_fallido(ip)
        registrar_auditoria(usuario, "LOGIN_FALLIDO", f"Motivo: {info}", ip)
        if info == 'usuario_inexistente':
            msg = 'Usuario no encontrado'
        elif info == 'sin_contrasena':
            msg = 'Su cuenta aún no tiene contraseña. Solicítela al administrador.'
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

    # Forzar cambio de contraseña si está marcado
    if info.get('debe_cambiar'):
        session['debe_cambiar'] = True
        return redirect(url_for('cambiar_contrasena_pagina', aviso=1))
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

@app.route('/cambiar_contrasena', methods=['GET', 'POST'])
@login_required
@csrf_protect
def cambiar_contrasena():
    usuario = session.get('usuario')
    ip = _ip_cliente()

    # GET: mostrar la página de cambio (usada también en el primer acceso forzado)
    if request.method == 'GET':
        forzado = bool(request.args.get('aviso') or session.get('debe_cambiar'))
        tiene = usuario_tiene_contrasena(usuario)
        titulo = "Cambiar Contraseña" if tiene else "Configurar Contraseña"
        campo_actual = ""
        if tiene and not session.get('debe_cambiar'):
            campo_actual = """
            <div class="mb-3">
                <label class="form-label">Contraseña actual</label>
                <input type="password" name="contrasena_actual" class="form-control" required autocomplete="current-password">
            </div>
            """
        aviso = ""
        if session.get('debe_cambiar') or request.args.get('aviso'):
            aviso = ('<div class="alert alert-warning">⚠️ Por seguridad, debe cambiar su contraseña '
                     'antes de continuar utilizando la plataforma.</div>')
        elif request.args.get('error'):
            aviso = ('<div class="alert alert-danger">❌ ' + html.escape(str(request.args.get('error'))) + '</div>')
        elif request.args.get('msg'):
            aviso = ('<div class="alert alert-success">✅ ' + html.escape(str(request.args.get('msg'))) + '</div>')

        page = CAMBIAR_CONTRASENA_TEMPLATE.format(
            titulo=titulo,
            usuario_actual=usuario,
            aviso=aviso,
            campo_actual=campo_actual,
            boton=titulo,
            enlace_salir=url_for('logout')
        )
        return _inyectar_csrf(page)

    # POST: procesar el cambio
    forzado = session.get('debe_cambiar') or request.form.get('forzado') == '1'

    nueva = request.form.get('nueva_contrasena', '')
    confirmar = request.form.get('confirmar_contrasena', '')

    # En cambio forzado la contraseña actual ya fue validada en el login.
    if usuario_tiene_contrasena(usuario) and not forzado:
        actual = request.form.get('contrasena_actual', '')
        if not verificar_credenciales(usuario, actual)[0]:
            registrar_auditoria(usuario, "CAMBIO_CLAVE_RECHAZADO", "Contraseña actual incorrecta", ip)
            return redirect(url_for('cambiar_contrasena_pagina', error='La contraseña actual es incorrecta'))

    if nueva != confirmar:
        return redirect(url_for('cambiar_contrasena_pagina', error='Las contraseñas no coinciden'))

    if len(nueva) < 6:
        return redirect(url_for('cambiar_contrasena_pagina', error='La contraseña debe tener al menos 6 caracteres'))

    ok, msg = establecer_contrasena(usuario, nueva, limpiar_debe_cambiar=True)
    accion = "CONTRASENA_INICIAL" if not usuario_tiene_contrasena(usuario) else "CAMBIO_CONTRASENA"
    registrar_auditoria(usuario, accion, msg, ip)

    # Limpiar flag de cambio forzado en la sesión
    session.pop('debe_cambiar', None)

    if not ok:
        return redirect(url_for('cambiar_contrasena_pagina', error=msg))
    if forzado:
        return redirect(url_for('cambiar_contrasena_pagina', msg='✅ Contraseña actualizada. Ya puede continuar. Bienvenido.'))
    return redirect(url_for('gestion', msg='Contraseña actualizada correctamente'))


@app.route('/cambiar_contrasena_pagina')
@login_required
def cambiar_contrasena_pagina():
    if request.args.get('aviso'):
        session['debe_cambiar'] = True
    args = {}
    if request.args.get('error'):
        args['error'] = request.args.get('error')
    if request.args.get('msg'):
        args['msg'] = request.args.get('msg')
    return redirect(url_for('cambiar_contrasena', **args))


# =============================================================================
# GESTIÓN
# =============================================================================

@app.route('/gestion')
@login_required
@cambio_requerido
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
    if es_admin:
        gestion_personal = generar_gestion_actividades_personales_por_usuario()
    else:
        gestion_personal = generar_gestion_actividades_personales(usuario_actual)

    extra = generar_gestion_contrasena(usuario_actual)
    if es_admin:
        extra += generar_gestion_auditoria()

    contrato_vals = {}
    try:
        cfg = obtener_configuracion_usuario(usuario_actual)
        datos_contrato = cfg.get('datos_contrato', {}) if cfg else {}
        contrato_vals = {
            clave: html.escape(str(datos_contrato.get(clave, '') or ''))
            for clave in ('nro', 'objeto', 'nombre', 'cedula', 'supervisor')
        }
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


@app.route('/asignar_contrasena', methods=['POST'])
@login_required
@admin_required
@csrf_protect
def asignar_contrasena():
    ip = _ip_cliente()
    target = sanitizar(request.form.get('usuario'), 50)
    nueva = request.form.get('nueva_contrasena', '')
    forzar = request.form.get('forzar_cambio') == '1'

    data = cargar_usuarios()
    if target not in data.get("usuarios", []):
        return redirect(url_for('gestion', error='Usuario no encontrado'))

    if len(nueva) < 6:
        return redirect(url_for('gestion', error='La contraseña debe tener al menos 6 caracteres'))

    ok, msg = establecer_contrasena(target, nueva, limpiar_debe_cambiar=not forzar)
    if not ok:
        return redirect(url_for('gestion', error=msg))

    if forzar:
        marcar_debe_cambiar_contrasena(target, True)
        detalle = f"Contraseña asignada a {target} (requiere cambio)"
    else:
        detalle = f"Contraseña asignada a {target}"

    registrar_auditoria(session.get('usuario'), "ASIGNAR_CONTRASENA", detalle, ip)
    return redirect(url_for('gestion', msg=f'Contraseña actualizada para {target}'))


@app.route('/guardar_datos_contrato', methods=['POST'])
@login_required
@csrf_protect
def guardar_datos_contrato():
    ip = _ip_cliente()
    usuario = session.get('usuario')
    datos = {
        'nro': sanitizar(request.form.get('nro'), 100),
        'objeto': sanitizar(request.form.get('objeto'), 500),
        'nombre': sanitizar(request.form.get('nombre'), 150),
        'cedula': sanitizar(request.form.get('cedula'), 50),
        'supervisor': sanitizar(request.form.get('supervisor'), 150)
    }
    try:
        guardar_configuracion_usuario(usuario, {'datos_contrato': datos})
        registrar_auditoria(usuario, "CONFIG_CONTRATO", "Datos de contrato actualizados", ip)
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
            aplicar_password_admin_inicial()
        logger.info("Aplicación inicializada correctamente (Usuarios, Config, Excel)")
    except Exception:
        logger.exception("Error durante la inicialización")
        raise


initialize_app()

if __name__ == '__main__':
    print("Iniciando servidor Flask local...")
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
