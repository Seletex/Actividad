# -*- coding: utf-8 -*-
"""
setup_admin.py - Establece la contraseña del usuario 'admin' de la app web.
Ejecutar una sola vez (o para restablecer) desde el equipo/servidor donde corre la app:
    python setup_admin.py

Requisitos mínimos: 6 caracteres. Opcionalmente se puede forzar el cambio
en el próximo ingreso.
"""

import getpass
import sys

from database import (
    cargar_usuarios, establecer_contrasena, marcar_debe_cambiar_contrasena
)


def principal():
    data = cargar_usuarios()
    usuarios = data.get("usuarios", [])

    if "admin" not in usuarios:
        print("ERROR: el usuario 'admin' no existe en la base de datos.")
        print("Usuarios disponibles:", ", ".join(usuarios))
        sys.exit(1)

    print("=" * 55)
    print("  CONFIGURACIÓN DE LA CONTRASEÑA DEL ADMINISTRADOR")
    print("=" * 55)
    print()
    print("Este paso le permite al usuario 'admin' iniciar sesión")
    print("en la plataforma web y asignar contraseñas a los demás usuarios.")
    print()

    # Confirmación de intención (evitar ejecuciones accidentales)
    resp = input("¿Desea continuar? (s/N): ").strip().lower()
    if resp != "s":
        print("Operación cancelada.")
        sys.exit(0)

    # Contraseña nueva (primer ingreso)
    nueva = getpass.getpass("Nueva contraseña para 'admin' (mínimo 6 caracteres): ").strip()
    if len(nueva) < 6:
        print("ERROR: la contraseña debe tener al menos 6 caracteres.")
        sys.exit(1)

    confirmar = getpass.getpass("Repita la contraseña: ").strip()
    if nueva != confirmar:
        print("ERROR: las contraseñas no coinciden.")
        sys.exit(1)

    # Opción de forzar cambio en el próximo ingreso
    forzar = input("¿Forzar que 'admin' la cambie en el próximo ingreso? (s/N): ").strip().lower() == "s"

    ok, msg = establecer_contrasena("admin", nueva, limpiar_debe_cambiar=not forzar)
    if not ok:
        print(f"ERROR: {msg}")
        sys.exit(1)

    if forzar:
        marcar_debe_cambiar_contrasena("admin", True)

    print()
    print("✔ Contraseña de 'admin' configurada correctamente.")
    if forzar:
        print("  Se pedirá que la cambie en su próximo ingreso.")
    print("  Ahora puede iniciar sesión en la web y asignar contraseñas")
    print("  desde Gestión > Usuarios del Sistema.")
    print()


if __name__ == "__main__":
    principal()
