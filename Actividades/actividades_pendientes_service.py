"""Genera el Excel con las actividades que a un usuario le faltan.

Por que existe
--------------
Registrar una actividad obliga a abrir el formulario, elegirla de una lista y
guardar: un registro a la vez. Cuando el usuario tiene varias actividades sin
registrar (por ejemplo al iniciar un mes o al cambiar de contrato), eso son
muchas vueltas.

Este servicio arma una hoja de trabajo con esas actividades ya escritas, para
que la persona solo complete fecha, cumplimiento, dependencia y solicitante, y
suba el archivo una sola vez.

Decisiones de seguridad
-----------------------
- La hoja se arma para un usuario concreto, tomado de la sesion. El archivo
  generado lleva su nombre, pero al importar **nunca** se usa el nombre que
  viene en el archivo: si alguien altera esa columna, los registros siguen
  siendo suyos. Asi nadie puede registrar labor ajena.
- Cada fila lleva una CLAVE opaca. Al importar se valida contra las actividades
  que el usuario tiene asignadas: si la clave no corresponde, la fila se rechaza
  con un motivo claro en vez de crear una actividad inventada.
- El texto de la actividad va precargado. No hace falta escribirlo y no se
  pueden crear duplicados por teclearlo de otra forma.
"""

import difflib
import hashlib
import io
import re
import unicodedata
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import database as db
from config import logger

# Columnas de la hoja, en orden.
COLUMNAS = [
    "CLAVE",
    "TIPO DE ACTIVIDAD",
    "FECHA",
    "FECHA ATENCIÓN",
    "CUMPLIDO",
    "DEPENDENCIA",
    "SOLICITANTE",
    "TIPO DE SOLICITUD",
    "MEDIO DE SOLICITUD",
    "DESCRIPCIÓN",
    "OBSERVACIONES",
]

# Anchos de columna para que se lea sin ajustar a mano.
_ANCHOS = {
    "CLAVE": 10,
    "TIPO DE ACTIVIDAD": 62,
    "FECHA": 20,
    "FECHA ATENCIÓN": 16,
    "CUMPLIDO": 12,
    "DEPENDENCIA": 26,
    "SOLICITANTE": 26,
    "TIPO DE SOLICITUD": 20,
    "MEDIO DE SOLICITUD": 20,
    "DESCRIPCIÓN": 40,
    "OBSERVACIONES": 30,
}

ENCABEZADO_CUMPLIDO = {
    "CUMPLIDO": ["Sí", "No"],
}

# Nombres de las hojas. Deben ser distintos: si coinciden, Excel renombra una
# y los menus desplegables dejan de encontrar la lista.
HOJA_ACTIVIDADES = "ACTIVIDADES"
HOJA_LISTAS = "LISTAS"


# =============================================================================
# COMPARACIÓN DE ACTIVIDADES
# =============================================================================

def normalizar_actividad(texto):
    """Normaliza para comparar: sin numeración, sin tildes y sin espacios extra."""
    limpio = unicodedata.normalize("NFKC", str(texto or "")).strip().casefold()
    limpio = unicodedata.normalize("NFKD", limpio)
    limpio = limpio.encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"^\s*\d+\s*[.)-]\s*", "", limpio)
    return re.sub(r"\s+", " ", limpio).strip()


def _numero_de_actividad(texto):
    """Numero inicial de una actividad, o None si no viene numerada."""
    coincidencia = re.match(r"^\s*(\d+)\s*[.)-]", str(texto or ""))
    return coincidencia.group(1) if coincidencia else None


def actividades_son_similares(primera, segunda, umbral=0.90):
    """True si dos textos describen la misma actividad.

    Hay dos señales, y hacen falta las dos:

    1. El texto normalizado es identico (sin numeracion, tildes ni espacios).
    2. El texto es muy parecido **y** las dos actividades llevan el mismo
       numero inicial.

    El numero importa mucho. Los contratos suelen repetir una frase larga al
    final de cada actividad, asi que dos actividades distintas pueden parecerse
    bastante sin ser la misma. En cambio, dos actividades con el mismo numero
    (las dos "4.") que se parecen un 92% casi con seguridad son la misma, escrita
    de dos formas. Asi se evita unir actividades que si son distintas.
    """
    clave_primera = normalizar_actividad(primera)
    clave_segunda = normalizar_actividad(segunda)
    if not clave_primera or not clave_segunda:
        return False
    if clave_primera == clave_segunda:
        return True

    numero_primera = _numero_de_actividad(primera)
    numero_segunda = _numero_de_actividad(segunda)
    if numero_primera is None or numero_primera != numero_segunda:
        # Sin el mismo numero solo se acepta una coincidencia casi exacta.
        return difflib.SequenceMatcher(
            None, clave_primera, clave_segunda
        ).ratio() >= 0.97

    return difflib.SequenceMatcher(
        None, clave_primera, clave_segunda
    ).ratio() >= umbral


def _clave_de_actividad(usuario, actividad):
    """Clave corta y estable para una actividad asignada."""
    base = f"{usuario}|{normalizar_actividad(actividad)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]


# =============================================================================
# ACTIVIDADES PENDIENTES
# =============================================================================

def actividades_registradas(usuario):
    """Actividades que el usuario ya tiene registradas (texto de cada fila)."""
    df = db.cargar_registros(usuario)
    if df.empty or "TIPO DE ACTIVIDAD" not in df.columns:
        return []
    textos = df["TIPO DE ACTIVIDAD"].fillna("").astype(str).tolist()
    return [t for t in textos if t.strip()]


def actividades_pendientes(usuario):
    """Actividades asignadas al usuario que no tiene ningun registro.

    Devuelve una lista de diccionarios con ``clave`` y ``actividad``.
    """
    if not usuario or usuario == "admin":
        # El administrador no registra actividades de contrato.
        return []

    asignadas = db.cargar_actividades(usuario)
    if not asignadas:
        return []

    registradas = actividades_registradas(usuario)

    # Primero se agrupan las asignadas por similaridad, para no repetir una
    # actividad que ya esta escrita de otra forma.
    grupos = []
    for actividad in asignadas:
        for grupo in grupos:
            if actividades_son_similares(actividad, grupo[0]):
                grupo.append(actividad)
                break
        else:
            grupos.append([actividad])

    pendientes = []
    for grupo in grupos:
        # Se descarta el grupo si alguna de sus variantes ya fue registrada.
        if any(
            actividades_son_similares(asignada, registrada)
            for asignada in grupo
            for registrada in registradas
        ):
            continue
        # Si hay varias variantes, se ofrece la version oficial (la primera).
        pendientes.append({
            "clave": _clave_de_actividad(usuario, grupo[0]),
            "actividad": grupo[0],
            "variantes": len(grupo),
        })

    return pendientes


# =============================================================================
# GENERACIÓN DEL EXCEL
# =============================================================================

def _estilo_encabezado(celda):
    celda.font = Font(bold=True, color="FFFFFF")
    celda.fill = PatternFill("solid", fgColor="1F4E78")
    celda.alignment = Alignment(vertical="center", wrap_text=True)


def generar_excel_pendientes(usuario):
    """Arma el archivo .xlsx con las actividades pendientes del usuario.

    Devuelve los bytes del archivo, o ``None`` si el usuario no tiene
    actividades asignadas.
    """
    pendientes = actividades_pendientes(usuario)

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = HOJA_ACTIVIDADES

    for indice, nombre in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(row=1, column=indice, value=nombre)
        _estilo_encabezado(celda)
        hoja.column_dimensions[get_column_letter(indice)].width = _ANCHOS.get(nombre, 20)
    hoja.row_dimensions[1].height = 32
    hoja.freeze_panes = "A2"

    # Las actividades que no se deben tocar: van precargadas y bloqueadas.
    idx_actividad = COLUMNAS.index("TIPO DE ACTIVIDAD") + 1
    idx_clave = COLUMNAS.index("CLAVE") + 1

    if not pendientes:
        hoja.cell(row=2, column=idx_actividad,
                  value=("No tienes actividades asignadas sin registrar. "
                         "Ponte en contacto con el administrador si esperabas "
                         "tener alguna."))
        return _a_bytes(libro)

    for fila, pendiente in enumerate(pendientes, start=2):
        hoja.cell(row=fila, column=idx_clave, value=pendiente["clave"])
        celda_actividad = hoja.cell(row=fila, column=idx_actividad,
                                    value=pendiente["actividad"])
        celda_actividad.alignment = Alignment(vertical="top", wrap_text=True)
        # Fecha de atención con formato de fecha real de Excel.
        for nombre in ("FECHA", "FECHA ATENCIÓN"):
            columna = COLUMNAS.index(nombre) + 1
            hoja.cell(row=fila, column=columna).number_format = "AAAA-MM-DD HH:MM:SS" \
                if nombre == "FECHA" else "AAAA-MM-DD"

    ultima = len(pendientes) + 1

    # Primero la hoja con los valores sugeridos: los menus desplegables la
    # necesitan para apuntar a sus rangos, asi que debe existir antes.
    _agregar_hoja_rutina(libro)
    _agregar_validaciones(hoja, ultima, idx_actividad, idx_clave)

    return _a_bytes(libro)


def _agregar_validaciones(hoja, ultima_fila, idx_actividad, idx_clave):
    """Menús desplegables para los campos que salen de listas."""
    validadores = []
    if db.cargar_tipos_solicitud():
        validadores.append(("TIPO DE SOLICITUD", db.cargar_tipos_solicitud()))
    if db.cargar_medios_solicitud():
        validadores.append(("MEDIO DE SOLICITUD", db.cargar_medios_solicitud()))
    if db.cargar_ubicaciones():
        validadores.append(("DEPENDENCIA", db.cargar_ubicaciones()))
    validadores.append(("CUMPLIDO", ENCABEZADO_CUMPLIDO["CUMPLIDO"]))

    hoja_rutina = hoja.parent[HOJA_LISTAS]
    for indice, (nombre, valores) in enumerate(validadores, start=1):
        if not valores:
            continue
        # La lista vive en la hoja de ayuda para que Excel la acepte.
        for fila, valor in enumerate(valores, start=2):
            hoja_rutina.cell(row=fila, column=indice, value=valor)

        referencia = f"'{hoja_rutina.title}'!${get_column_letter(indice)}$2" \
                     f":${get_column_letter(indice)}${len(valores) + 1}"
        validacion = DataValidation(
            type="list",
            formula1=f"={referencia}",
            allow_blank=True,
            showErrorMessage=True,
            errorTitle="Valor no permitido",
            error=("Elija un valor de la lista. Si falta el dato que necesita, "
                   "escribalo en Observaciones."),
        )
        hoja.add_data_validation(validacion)
        columna = COLUMNAS.index(nombre) + 1
        validacion.add(f"{get_column_letter(columna)}2:"
                       f"{get_column_letter(columna)}{max(ultima_fila, 2)}")

    # La actividad viene precargada: no debe editarse. Para bloquearla la
    #formula debe evaluar falso; con una verdadera Excel la permitiria.
    validacion_texto = DataValidation(
        type="custom",
        formula1="=0",
        allow_blank=False,
        showErrorMessage=True,
        errorTitle="Actividad del contrato",
        error=("El texto de la actividad viene precargado y no se puede cambiar. "
               "Complete los demas datos de la fila."),
    )
    hoja.add_data_validation(validacion_texto)
    validacion_texto.add(f"{get_column_letter(idx_actividad)}2:"
                         f"{get_column_letter(idx_actividad)}{max(ultima_fila, 2)}")


def _agregar_hoja_rutina(libro):
    hoja = libro.create_sheet(HOJA_LISTAS)
    titulos = ["TIPO DE SOLICITUD", "MEDIO DE SOLICITUD", "DEPENDENCIA", "CUMPLIDO"]
    for indice, titulo in enumerate(titulos, start=1):
        celda = hoja.cell(row=1, column=indice, value=titulo)
        _estilo_encabezado(celda)
        hoja.column_dimensions[get_column_letter(indice)].width = 28

    instrucciones = [
        "COMO USAR ESTE ARCHIVO",
        "",
        "1. No cambie la columna CLAVE ni el texto de TIPO DE ACTIVIDAD: ya vienen "
        "escritos con la actividad de su contrato.",
        "2. Complete FECHA (dia y mes del registro) y CUMPLIDO.",
        "3. Si realizo el trabajo en otro dia, escriba tambien FECHA ATENCIÓN.",
        "4. Los menus desplegables traen los valores que ya usa la entidad.",
        "5. En DEPENDENCIA, SOLICITANTE, DESCRIPCIÓN y OBSERVACIONES escriba con "
        "palabras propias, sin copiar y pegar de otra fila.",
        "6. Guarde el archivo y subalo desde esta misma pantalla.",
        "",
        "Cada fila que se suba quedara registrada con su usuario y con la fecha "
        "de hoy, por seguridad.",
    ]
    for indice, linea in enumerate(instrucciones, start=6):
        hoja.cell(row=indice, column=1, value=linea)
    hoja.column_dimensions["A"].width = 90


def _a_bytes(libro):
    memoria = io.BytesIO()
    libro.save(memoria)
    return memoria.getvalue()


# =============================================================================
# LECTURA DEL ARCHIVO DEVUELTO POR EL USUARIO
# =============================================================================

class ResultadoLectura:
    """Resumen de lo que se leyo del archivo, con los problemas encontrados."""

    def __init__(self):
        self.filas = []
        self.problemas = []

    @property
    def validas(self):
        return [f for f in self.filas if f.get("ok")]

    @property
    def descartadas(self):
        return [f for f in self.filas if not f.get("ok")]

    def resumen_texto(self):
        partes = [f"{len(self.validas)} registro(s) listo(s) para guardar"]
        if self.descartadas:
            partes.append(f"{len(self.descartadas)} fila(s) con problemas")
        return ". ".join(partes) + "."


def _valor(celda):
    if celda is None:
        return ""
    valor = celda.value
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor.strip()
    if hasattr(valor, "strftime"):
        if valor.hour or valor.minute or valor.second:
            return valor.strftime("%Y-%m-%d %H:%M:%S")
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def leer_archivo_pendientes(ruta, usuario):
    """Lee el archivo del usuario y valida cada fila.

    Nunca toma el usuario del archivo: todas las filas se atribuyen a
    ``usuario``, que viene de la sesion.
    """
    resultado = ResultadoLectura()
    if not usuario or usuario == "admin":
        return resultado

    libro = openpyxl.load_workbook(ruta, data_only=True)
    hoja = libro[HOJA_ACTIVIDADES] if HOJA_ACTIVIDADES in libro.sheetnames else libro.worksheets[0]

    encabezados = {}
    for indice in range(1, hoja.max_column + 1):
        nombre = str(hoja.cell(row=1, column=indice).value or "").strip().upper()
        encabezados[nombre] = indice

    if "TIPO DE ACTIVIDAD" not in encabezados or "FECHA" not in encabezados:
        resultado.problemas.append(
            "El archivo no tiene las columnas TIPO DE ACTIVIDAD y FECHA. "
            "Descargue la plantilla de nuevo."
        )
        return resultado

    asignadas = db.cargar_actividades(usuario)
    claves_validas = {_clave_de_actividad(usuario, a): a for a in asignadas}

    fila_indice = 1
    for fila in range(2, hoja.max_row + 1):
        fila_indice += 1
        valores = {
            nombre: _valor(hoja.cell(row=fila, column=columna))
            for nombre, columna in encabezados.items()
        }
        actividad_texto = valores.get("TIPO DE ACTIVIDAD", "")
        if not actividad_texto and not valores.get("CLAVE"):
            continue  # fila vacia

        # Fila que el usuario no toco: se ignora en silencio. La plantilla trae
        # todas las actividades pendientes, y lo normal es llenarlas solo
        # algunas; avisar de las demas seria un ruido constante.
        if not (valores.get("FECHA") or valores.get("FECHA ATENCIÓN")
                or valores.get("CUMPLIDO")):
            continue

        registro, problema = _validar_fila(
            valores, claves_validas, asignadas, usuario
        )
        registro["fila"] = fila_indice
        if problema:
            resultado.filas.append(registro)
            resultado.problemas.append(f"Fila {fila_indice}: {problema}")
        else:
            resultado.filas.append(registro)

    return resultado


def _validar_fila(valores, claves_validas, asignadas, usuario):
    """Valida una fila. Devuelve (registro, problema)."""
    problema = ""
    clave = valores.get("CLAVE", "")
    actividad_texto = valores.get("TIPO DE ACTIVIDAD", "")

    # 1. Resolver la actividad: primero por la clave, luego por el texto.
    actividad_oficial = ""
    if clave and clave in claves_validas:
        actividad_oficial = claves_validas[clave]
    elif clave:
        # La clave no corresponde a este usuario: se descarta la fila.
        return {
            "ok": False,
            "clave": clave,
            "actividad": actividad_texto,
            "motivo": "la clave no pertenece a sus actividades",
        }, "la clave no corresponde a ninguna actividad asignada a usted"
    elif actividad_texto:
        for candidata in asignadas:
            if actividades_son_similares(actividad_texto, candidata):
                actividad_oficial = candidata
                break

    if not actividad_oficial:
        # Sin clave y con texto irreconocible: se descarta.
        return {
            "ok": False,
            "clave": "",
            "actividad": actividad_texto,
            "motivo": "actividad no asignada",
        }, "la actividad escrita no está en su lista. Use el archivo descargado del sistema."

    fecha = valores.get("FECHA", "")
    fecha_atencion = valores.get("FECHA ATENCIÓN", "")
    cumplido = (valores.get("CUMPLIDO", "") or "").strip()

    # 2. Fecha: se acepta la de atención si la de solicitud falta.
    fecha_principal = fecha or fecha_atencion
    if not fecha_principal:
        return {
            "ok": False, "clave": clave, "actividad": actividad_oficial,
            "motivo": "sin fecha",
        }, "falta la columna FECHA (y la de atención)"

    if not fecha and fecha_atencion:
        fecha = f"{fecha_atencion} 00:00:00"

    if not fecha_atencion:
        fecha_atencion = fecha[:10]

    # 3. Cumplimiento con las dos grafias habituales.
    if complied := _normalizar_cumplido(cumplido):
        cumplido = complied
    else:
        return {
            "ok": False, "clave": clave, "actividad": actividad_oficial,
            "motivo": "cumplimiento invalido",
        }, "CUMPLIDO debe ser 'Sí' o 'No'"

    registro = {
        "ok": True,
        "clave": clave,
        "usuario": usuario,          # siempre el de la sesion, nunca el del archivo
        "actividad": actividad_oficial,
        "fecha": fecha,
        "fecha_atencion": fecha_atencion,
        "cumplido": cumplido,
        "dependencia": valores.get("DEPENDENCIA", ""),
        "solicitante": valores.get("SOLICITANTE", ""),
        "tipo_solicitud": valores.get("TIPO DE SOLICITUD", ""),
        "medio_solicitud": valores.get("MEDIO DE SOLICITUD", ""),
        "descripcion": valores.get("DESCRIPCIÓN", ""),
        "observaciones": valores.get("OBSERVACIONES", ""),
    }
    return registro, problema


def _normalizar_cumplido(texto):
    """Acepta Sí/No con o sin tilde, en mayúsculas o minúsculas."""
    limpio = str(texto or "").strip().strip(".").casefold()
    if limpio in ("si", "sí", "s", "yes", "1", "true"):
        return "Sí"
    if limpio in ("no", "n", "0", "false"):
        return "No"
    return ""


# =============================================================================
# GUARDADO
# =============================================================================

def guardar_registros_pendientes(usuario, filas):
    """Guarda las filas validas como registros del usuario.

    Devuelve un diccionario con los conteos. Si una fila falla al guardarse, se
    avisa y se sigue con las demas: un error aislado no debe tumbar la carga.
    """
    guardados = 0
    errores = []
    for fila in filas:
        if not fila.get("ok"):
            continue
        registro = {
            "USUARIO": usuario,
            "FECHA": fila["fecha"],
            "TIPO DE ACTIVIDAD": fila["actividad"],
            "DEPENDENCIA": fila["dependencia"],
            "SOLICITANTE": fila["solicitante"],
            "TIPO DE SOLICITUD": fila["tipo_solicitud"],
            "MEDIO DE SOLICITUD": fila["medio_solicitud"],
            "DESCRIPCIÓN": fila["descripcion"],
            "CUMPLIDO": fila["cumplido"],
            "FECHA ATENCIÓN": fila["fecha_atencion"],
            "OBSERVACIONES": fila["observaciones"],
        }
        try:
            if db.guardar_registro(registro):
                guardados += 1
            else:
                errores.append(f"La fila {fila.get('fila')} no se pudo guardar")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error guardando actividad pendiente")
            errores.append(f"La fila {fila.get('fila')} dio error: {exc}")

    return {"guardados": guardados, "errores": errores}
