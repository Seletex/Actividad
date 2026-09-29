"""
Bootstrap seguro del administrador para despliegues sin acceso a shell.

Se usa la variable de entorno ADMIN_INITIAL_PASSWORD. La contraseña solo se
aplica cuando el usuario 'admin' todavía no tiene una contraseña configurada.
Después del primer ingreso la aplicación exige cambiarla.
"""

import os

from config import logger
from database import (
    establecer_contrasena,
    usuario_tiene_contrasena,
)


MINIMO_LONGITUD = 10


def aplicar_password_admin_inicial():
    """Configura el primer acceso de admin si se solicitó mediante entorno.

    Devuelve ``True`` solo cuando se aplicó una contraseña nueva. Nunca
    sobrescribe una contraseña existente.
    """
    password = os.environ.get("ADMIN_INITIAL_PASSWORD", "")
    if not password:
        return False

    if usuario_tiene_contrasena("admin"):
        logger.info("Bootstrap admin omitido: el usuario ya tiene contraseña")
        return False

    if len(password) < MINIMO_LONGITUD:
        raise RuntimeError(
            "ADMIN_INITIAL_PASSWORD debe tener al menos "
            f"{MINIMO_LONGITUD} caracteres"
        )

    ok, mensaje = establecer_contrasena(
        "admin", password, limpiar_debe_cambiar=False
    )
    if not ok:
        raise RuntimeError(f"No se pudo configurar la contraseña inicial: {mensaje}")

    logger.warning(
        "Se configuró la contraseña inicial de admin mediante "
        "ADMIN_INITIAL_PASSWORD; se exigirá cambiarla en el primer ingreso"
    )
    return True
