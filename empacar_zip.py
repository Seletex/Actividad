"""Empaqueta la version PHP para subirla a 260mb.net.

Genera ``php_260mb_deploy.zip`` con el contenido de la carpeta ``php``.
Incluye la copia de datos (datos/datos_iniciales.json y el SQL) y la
configuracion local de MySQL, porque el paquete es para el hosting del
usuario. No incluye archivos temporales, bases SQLite ni copias de respaldo
antiguas.
"""

import os
import zipfile

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "php")
ZIP_SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "php_260mb_deploy.zip")

HTACCESS = """# Pagina inicial
DirectoryIndex index.php

# Codificacion
AddDefaultCharset UTF-8

<IfModule mod_rewrite.c>
    RewriteEngine On
    RewriteRule ^config\\.local\\.php$ - [F,L]
    RewriteRule ^datos/ - [F,L]
    RewriteRule ^sql/ - [F,L]
    RewriteRule ^lib/ - [F,L]
    RewriteRule ^views/ - [F,L]
</IfModule>
"""

EXCLUIR_ARCHIVOS = {".gitkeep"}
EXCLUIR_CARPETAS = {"respaldos", ".git"}


def incluir(ruta_relativa):
    partes = ruta_relativa.replace("\\", "/").split("/")
    if any(parte in EXCLUIR_CARPETAS for parte in partes[:-1]):
        return False
    nombre = partes[-1]
    if nombre in EXCLUIR_ARCHIVOS:
        return False
    if nombre.endswith((".sqlite", ".sqlite3", ".db", ".log")):
        return False
    if nombre.startswith("~$"):
        return False
    return True


def main():
    with open(os.path.join(BASE_DIR, ".htaccess"), "w", encoding="utf-8") as archivo:
        archivo.write(HTACCESS)

    if os.path.exists(ZIP_SALIDA):
        os.remove(ZIP_SALIDA)

    incluidos = []
    with zipfile.ZipFile(ZIP_SALIDA, "w", zipfile.ZIP_DEFLATED) as zf:
        for raiz, carpetas, archivos in os.walk(BASE_DIR):
            carpetas[:] = [c for c in carpetas if c not in EXCLUIR_CARPETAS]
            for nombre in archivos:
                ruta_completa = os.path.join(raiz, nombre)
                ruta_relativa = os.path.relpath(ruta_completa, BASE_DIR)
                if not incluir(ruta_relativa):
                    continue
                zf.write(ruta_completa, ruta_relativa.replace("\\", "/"))
                incluidos.append(ruta_relativa.replace("\\", "/"))

    tamano = os.path.getsize(ZIP_SALIDA)
    print("ZIP generado: %s" % ZIP_SALIDA)
    print("Tamano: %.1f MB" % (tamano / (1024 * 1024)))
    print("Archivos incluidos: %d" % len(incluidos))
    for nombre in sorted(incluidos):
        print("  " + nombre)


if __name__ == "__main__":
    main()
