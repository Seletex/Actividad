"""
web_security.py - Utilidades de seguridad para la versión web (Flask).
Incluye: protección CSRF, rate limiting de login, headers de seguridad,
sanitización de entradas y sesiones reforzadas.
Este módulo solo se usa en app.py (web), no en la app de escritorio.
"""

import re
import time
import secrets
import threading
from collections import defaultdict, deque
from functools import wraps
from flask import session, request, redirect, url_for, make_response

import config as config_mod
from config import logger


# =============================================================================
# CSRF (Cross-Site Request Forgery)
# =============================================================================

def generar_csrf_token():
    """Genera (una vez por sesión) el token CSRF y lo guarda en la sesión."""
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_hex(32)
        session['csrf_token'] = token
    return token


def csrf_protect(f):
    """Decorador: valida el token CSRF en toda petición POST."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'POST':
            token = session.get('csrf_token')
            form_token = request.form.get('csrf_token', '')
            header_token = request.headers.get('X-CSRFToken', '')
            if not token or not (form_token and secrets.compare_digest(token, form_token)) \
               and not (header_token and secrets.compare_digest(token, header_token)):
                logger.warning(f"CSRF rechazado ({request.remote_addr}) -> {request.path}")
                return redirect(url_for('index', error='Sesión expirada. Intente nuevamente.'))
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# RATE LIMITING (antifuerza bruta en el login)
# =============================================================================

# Ventana en segundos y máximo de intentos por dirección IP
_RATE_LIMIT_WINDOW = 15 * 60
_RATE_LIMIT_MAX = 10

# Almacenamiento en memoria: ip -> deque de timestamps
_login_attempts = defaultdict(deque)
_rate_lock = threading.Lock()


def _limpiar_esquemas(deque_obj):
    corte = time.time() - _RATE_LIMIT_WINDOW
    while deque_obj and deque_obj[0] < corte:
        deque_obj.popleft()


def login_bloqueado(ip):
    """True si la IP ha excedido el máximo de intentos fallidos en la ventana."""
    if not ip:
        return False
    with _rate_lock:
        dq = _login_attempts[ip]
        _limpiar_esquemas(dq)
        return len(dq) >= _RATE_LIMIT_MAX


def registrar_intento_fallido(ip):
    """Registra un intento de login fallido para la IP."""
    if not ip:
        return
    with _rate_lock:
        dq = _login_attempts[ip]
        _limpiar_esquemas(dq)
        dq.append(time.time())


def registrar_intento_exitoso(ip):
    """Borra el historial de intentos fallidos para la IP tras un login exitoso."""
    with _rate_lock:
        _login_attempts.pop(ip, None)


# =============================================================================
# SANITIZACIÓN DE ENTRADAS
# =============================================================================

def sanitizar(texto, max_len=500):
    """Limpia y recorta texto de entrada; evita tags/scripts y espacios no deseados."""
    if texto is None:
        return ""
    if not isinstance(texto, str):
        texto = str(texto)
    texto = re.sub(r'<[^>]*>', '', texto)
    texto = texto.replace('\x00', '')
    return texto.strip()[:max_len]


def sanitizar_opcion(texto, opciones_validas):
    """Devuelve el texto solo si está dentro de las opciones válidas; si no, string vacío.
    Previene inyección/valores inválidos en selects."""
    t = sanitizar(texto, 120).lower()
    for op in opciones_validas:
        if op.lower() == t:
            return op
    return ""


# =============================================================================
# SEGURIDAD DE SESIÓN (Flask config)
# =============================================================================

def configurar_cookies(app):
    """Refuerza el manejo de cookies de sesión."""
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os_environ_truthy('SESSION_COOKIE_SECURE')
    app.config['PERMANENT_SESSION_LIFETIME'] = 12 * 60 * 60  # 12 horas
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True


def os_environ_truthy(key):
    try:
        import os
        return os.environ.get(key, '').lower() in ('1', 'true', 'yes', 'on')
    except Exception:
        return False


# =============================================================================
# HEADERS DE SEGURIDAD
# =============================================================================

def seguridad_headers(resp):
    """Agrega cabeceras de seguridad a la respuesta HTTP."""
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('X-XSS-Protection', '0')  # legacy; moderno vía CSP
    resp.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "font-src 'self' https://cdnjs.cloudflare.com data:; "
        "connect-src 'self'"
    )
    resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    # Cache-Control modesto para páginas autenticadas
    if request.path and not request.path.endswith(('.js', '.css', '.png', '.jpg', '.ico')):
        resp.headers.setdefault('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
    return resp
