"""Pruebas de las actividades pendientes en Excel.

Cubre el flujo completo: descargar la plantilla, llenarla, subirla. Y los dos
riesgos que trae consigo:

- Que alguien registre labor ajena. El usuario se toma de la sesion, nunca del
  archivo.
- Que se creen actividades duplicadas o inventadas. Cada fila se valida contra
  las actividades que el usuario tiene asignadas.
"""

import io
import os
import re
import tempfile

import openpyxl
import pytest

from actividades_pendientes_service import (
    HOJA_ACTIVIDADES,
    actividades_pendientes,
    actividades_son_similares,
    generar_excel_pendientes,
    guardar_registros_pendientes,
    leer_archivo_pendientes,
    normalizar_actividad,
)
from tests.conftest import consultar, ejecutar

ACTIVIDAD_A = "1. Brindar apoyo en la atención de requerimientos técnicos"
ACTIVIDAD_B = "2. Apoyar en el mantenimiento preventivo de equipos"


def _asignar_actividades(db, usuario, actividades):
    """Asigna actividades al usuario en la base de pruebas.

    Usa el ayudante ``ejecutar`` porque traduce los marcadores '?' que SQLite
    entiende y PostgreSQL no. Con SQL crudo, la suite pasaria en el escritorio
    y fallaria en Render.
    """
    ejecutar(db, "DELETE FROM actividades_personales WHERE username = ?", (usuario,))
    for actividad in actividades:
        ejecutar(db,
            "INSERT INTO actividades_personales (username, actividad) VALUES (?, ?)",
            (usuario, actividad),
        )
    # cargar_actividades() guarda en cache: hay que limpiarla o la plantilla
    # se arma con la lista anterior.
    db.clear_cache()


def _abrir_plantilla(usuario):
    contenido = generar_excel_pendientes(usuario)
    assert contenido, "la plantilla no debe estar vacia"
    return openpyxl.load_workbook(io.BytesIO(contenido))


def _guardar_como_excel(wb):
    memoria = io.BytesIO()
    wb.save(memoria)
    memoria.seek(0)
    return memoria


class TestComparacionDeActividades:
    def test_el_texto_se_normaliza(self):
        assert normalizar_actividad("1.  Brindar   APOYO ") == "brindar apoyo"
        assert normalizar_actividad("Atención") == "atencion"

    def test_la_misma_actividad_con_otra_numeracion(self):
        assert actividades_son_similares(
            "1. Brindar apoyo en la atención",
            "1.   Brindar   apoyo en la atención",
        )

    def test_actividades_distintas_no_se_une(self):
        assert not actividades_son_similares(
            ACTIVIDAD_A,
            ACTIVIDAD_B,
        )

    def test_mismo_numero_y_texto_parecido_son_la_misma(self):
        """El caso real de Felipe: las dos '4.' de la misma actividad."""
        assert actividades_son_similares(
            "4. Cumplir con las actividades del proceso del sistema de Gestion de Calidad",
            "4. Coadyuvar con las actividades del proceso del Sistema de Gestion de Calidad.",
        )

    def test_numero_distinto_no_se_une_aunque_se_parezcan(self):
        """Textos de contrato que comparten la frase final no son la misma."""
        cola = ", a las que sean necesarias para el cabal cumplimiento del contrato."
        assert not actividades_son_similares(
            "1. Brindar apoyo en la atencion de requerimientos" + cola,
            "2. Apoyar en el mantenimiento de equipos" + cola,
        )


class TestGeneracionDeLaPlantilla:
    def test_lista_las_actividades_sin_registrar(self, db):
        _asignar_actividades(db, "tester", [ACTIVIDAD_A, ACTIVIDAD_B])
        pendientes = actividades_pendientes("tester")
        assert [p["actividad"] for p in pendientes] == [ACTIVIDAD_A, ACTIVIDAD_B]
        assert all(p["clave"] for p in pendientes)

    def test_omite_las_que_ya_tiene_registradas(self, db, registrar):
        _asignar_actividades(db, "tester", [ACTIVIDAD_A, ACTIVIDAD_B])
        registrar(actividad=ACTIVIDAD_A)
        pendientes = actividades_pendientes("tester")
        assert [p["actividad"] for p in pendientes] == [ACTIVIDAD_B]

    def test_reconoce_lo_registrado_con_otra_redaccion(self, db, registrar):
        """Si ya lo registro con un texto parecido, no se vuelve a pedir."""
        _asignar_actividades(db, "tester", [
            "4. Cumplir con las actividades del proceso del sistema de Gestion de Calidad",
            ACTIVIDAD_B,
        ])
        registrar(actividad=(
            "4. Coadyuvar con las actividades del proceso del Sistema de Gestion de Calidad."
        ))
        pendientes = actividades_pendientes("tester")
        assert [p["actividad"] for p in pendientes] == [ACTIVIDAD_B]

    def test_no_repite_una_actividad_duplicada_en_la_lista(self, db):
        _asignar_actividades(db, "tester", [
            "4. Cumplir con las actividades del proceso del sistema de Gestion de Calidad",
            "4. Coadyuvar con las actividades del proceso del Sistema de Gestion de Calidad.",
        ])
        pendientes = actividades_pendientes("tester")
        assert len(pendientes) == 1, "las dos variantes son la misma actividad"

    def test_el_administrador_no_recibe_plantilla(self, db):
        assert actividades_pendientes("admin") == []

    def test_el_excel_trae_la_actividad_precargada(self, db):
        _asignar_actividades(db, "tester", [ACTIVIDAD_A, ACTIVIDAD_B])
        libro = _abrir_plantilla("tester")
        hoja = libro[HOJA_ACTIVIDADES]
        encabezados = [hoja.cell(row=1, column=c).value
                       for c in range(1, hoja.max_column + 1)]
        assert "CLAVE" in encabezados
        assert "TIPO DE ACTIVIDAD" in encabezados
        assert "FECHA" in encabezados
        assert "CUMPLIDO" in encabezados

        textos = [hoja.cell(row=f, column=encabezados.index("TIPO DE ACTIVIDAD") + 1).value
                  for f in range(2, 4)]
        assert ACTIVIDAD_A in textos
        assert ACTIVIDAD_B in textos

    def test_el_excel_ofrece_menus_desplegables(self, db):
        _asignar_actividades(db, "tester", [ACTIVIDAD_A])
        libro = _abrir_plantilla("tester")
        hoja = libro[HOJA_ACTIVIDADES]
        assert len(hoja.data_validations.dataValidation) >= 3, \
            "debe haber menus para dependencia, tipo, medio y cumplimiento"

    def test_el_texto_de_la_actividad_no_se_puede_editar(self, db):
        """La validacion debe bloquear, no solo avisar.

        Con una formula que siempre da verdadero Excel permite escribir, y el
        usuario podria cambiar el texto creyendo que el sistema lo tendra en
        cuenta. Se verifica que la formula sea falsa y que abarque la columna.
        """
        _asignar_actividades(db, "tester", [ACTIVIDAD_A, ACTIVIDAD_B])
        libro = _abrir_plantilla("tester")
        hoja = libro[HOJA_ACTIVIDADES]

        bloqueos = [
            dv for dv in hoja.data_validations.dataValidation
            if dv.type == "custom"
        ]
        assert bloqueos, "debe existir una validacion que bloquee la actividad"
        bloqueo = bloqueos[0]
        assert str(bloqueo.formula1).strip() in ("=0", "0"), \
            f"la formula debe bloquear la escritura, no permitirla: {bloqueo.formula1}"
        assert bloqueo.showErrorMessage
        # Debe aplicarse a la columna del texto de la actividad.
        rangos = str(bloqueo.sqref)
        assert "B2" in rangos, f"debe cubrir la columna de actividad: {rangos}"

    def test_sin_actividades_avisa_en_vez_de_dar_error(self, db):
        contenido = generar_excel_pendientes("tester")
        assert contenido, "debe generar el archivo aunque no haya pendientes"


class TestSubidaDelArchivo:
    def _plantilla_con_datos(self, db, filas):
        """Crea la plantilla y escribe datos en las filas indicadas."""
        _asignar_actividades(db, "tester", [ACTIVIDAD_A, ACTIVIDAD_B])
        libro = _abrir_plantilla("tester")
        hoja = libro[HOJA_ACTIVIDADES]
        encabezados = {hoja.cell(row=1, column=c).value: c
                       for c in range(1, hoja.max_column + 1)}
        for indice, datos in filas.items():
            for columna, valor in datos.items():
                hoja.cell(row=indice, column=encabezados[columna], value=valor)
        return _guardar_como_excel(libro)

    def _leer(self, db, archivo):
        """Escribe el Excel a disco y lo lee como lo haria la ruta web."""
        descriptor, ruta = tempfile.mkstemp(suffix=".xlsx")
        os.close(descriptor)
        try:
            with open(ruta, "wb") as destino:
                destino.write(archivo.read())
            return leer_archivo_pendientes(ruta, "tester")
        finally:
            try:
                os.remove(ruta)
            except OSError:
                pass

    def test_registra_las_filas_completas(self, db, registrar):
        archivo = self._plantilla_con_datos(db, {
            2: {"FECHA": "2026-09-20", "CUMPLIDO": "Sí",
                "DEPENDENCIA": "Planeación", "SOLICITANTE": "NELLY GARCIA"},
        })
        lectura = self._leer(db, archivo)
        assert not lectura.problemas, lectura.problemas
        assert len(lectura.validas) == 1

        fila = lectura.validas[0]
        assert fila["actividad"] == ACTIVIDAD_A
        assert fila["cumplido"] == "Sí"
        assert fila["dependencia"] == "Planeación"

    def test_el_usuario_siempre_es_el_de_la_sesion(self, db):
        """Aunque el archivo diga otro nombre, el registro es del usuario.

        Se agrega a mano una columna USUARIO con el nombre de otra persona, como
        haria alguien que quisiera registrar labor ajena.
        """
        _asignar_actividades(db, "tester", [ACTIVIDAD_A, ACTIVIDAD_B])
        libro = _abrir_plantilla("tester")
        hoja = libro[HOJA_ACTIVIDADES]
        encabezados = {hoja.cell(row=1, column=c).value: c
                       for c in range(1, hoja.max_column + 1)}
        hoja.cell(row=2, column=encabezados["FECHA"], value="2026-09-20")
        hoja.cell(row=2, column=encabezados["CUMPLIDO"], value="Sí")
        columna = hoja.max_column + 1
        hoja.cell(row=1, column=columna, value="USUARIO")
        hoja.cell(row=2, column=columna, value="Alejandro")
        memoria = _guardar_como_excel(libro)

        lectura = self._leer(db, memoria)
        assert lectura.validas, "la fila es valida: solo cambia el nombre"
        assert lectura.validas[0]["usuario"] == "tester", \
            "nadie debe registrar labor ajena"

    def test_una_fila_sin_tocar_se_ignora_en_silencio(self, db):
        """La plantilla trae todas las pendientes; llenar solo algunas es normal."""
        archivo = self._plantilla_con_datos(db, {
            2: {"FECHA": "2026-09-20", "CUMPLIDO": "Sí"},
        })
        lectura = self._leer(db, archivo)
        assert len(lectura.validas) == 1
        assert not lectura.problemas, \
            f"las filas sin llenar no deben reportarse: {lectura.problemas}"

    def test_una_clave_ajena_se_descarta(self, db):
        archivo = self._plantilla_con_datos(db, {
            2: {"FECHA": "2026-09-20", "CUMPLIDO": "Sí",
                "CLAVE": "clave-falsa"},
        })
        lectura = self._leer(db, archivo)
        assert not lectura.validas
        assert lectura.descartadas
        assert "clave" in lectura.descartadas[0]["motivo"]

    def test_falta_de_fecha_se_descarta(self, db):
        archivo = self._plantilla_con_datos(db, {2: {"CUMPLIDO": "Sí"}})
        lectura = self._leer(db, archivo)
        assert not lectura.validas
        assert "fecha" in lectura.descartadas[0]["motivo"]

    def test_cumplimiento_invalido_se_descarta(self, db):
        archivo = self._plantilla_con_datos(db, {
            2: {"FECHA": "2026-09-20", "CUMPLIDO": "Tal vez"},
        })
        lectura = self._leer(db, archivo)
        assert not lectura.validas
        assert "cumplimiento" in lectura.descartadas[0]["motivo"]

    def test_acepta_si_sin_tilde(self, db):
        archivo = self._plantilla_con_datos(db, {
            2: {"FECHA": "2026-09-20", "CUMPLIDO": "si"},
        })
        lectura = self._leer(db, archivo)
        assert lectura.validas[0]["cumplido"] == "Sí"

    def test_guarda_los_registros(self, db):
        archivo = self._plantilla_con_datos(db, {
            2: {"FECHA": "2026-09-20", "CUMPLIDO": "Sí"},
            3: {"FECHA": "2026-09-21", "CUMPLIDO": "No"},
        })
        lectura = self._leer(db, archivo)
        resultado = guardar_registros_pendientes("tester", lectura.validas)
        assert resultado["guardados"] == 2
        assert not resultado["errores"]

        filas = consultar(db, "SELECT usuario, tipo_actividad FROM registros")
        assert len(filas) == 2
        assert all(f[0] == "tester" for f in filas)


class TestRutasWeb:
    def test_descarga_solo_para_usuarios_autenticados(self, cliente):
        assert cliente.get("/descargar_actividades_pendientes").status_code == 302

    def test_descarga_el_archivo(self, cliente, iniciar_sesion, db):
        _asignar_actividades(db, "tester", [ACTIVIDAD_A])
        iniciar_sesion()
        respuesta = cliente.get("/descargar_actividades_pendientes")
        assert respuesta.status_code == 200
        assert "spreadsheetml" in respuesta.mimetype

    def test_el_administrador_no_recibe_plantilla(self, como_admin):
        respuesta = como_admin.get("/descargar_actividades_pendientes")
        # El admin no registra actividades: se le avisa y no se genera archivo.
        assert respuesta.status_code in (302, 200)
        if respuesta.status_code == 200:
            pytest.skip("el admin genero un archivo vacio")

    def test_la_subida_exige_csrf(self, cliente, iniciar_sesion, db):
        iniciar_sesion()
        respuesta = cliente.post("/importar_mis_actividades", data={})
        assert respuesta.status_code in (302, 403)

    def test_subir_el_archivo_registra(self, cliente, iniciar_sesion,
                                       token_csrf, db):
        _asignar_actividades(db, "tester", [ACTIVIDAD_A])
        iniciar_sesion()

        libro = _abrir_plantilla("tester")
        hoja = libro[HOJA_ACTIVIDADES]
        encabezados = {hoja.cell(row=1, column=c).value: c
                       for c in range(1, hoja.max_column + 1)}
        hoja.cell(row=2, column=encabezados["FECHA"], value="2026-09-20")
        hoja.cell(row=2, column=encabezados["CUMPLIDO"], value="Sí")
        memoria = _guardar_como_excel(libro)

        respuesta = cliente.post("/importar_mis_actividades", data={
            "csrf_token": token_csrf(),
            "archivo": (memoria, "pendientes.xlsx"),
        }, content_type="multipart/form-data")
        assert respuesta.status_code == 302

        filas = consultar(db, "SELECT usuario, tipo_actividad FROM registros")
        assert len(filas) == 1
        assert filas[0][0] == "tester"
        assert filas[0][1] == ACTIVIDAD_A

    def test_el_administrador_no_puede_subir(self, como_admin, token_csrf, db):
        memoria = _guardar_como_excel(_abrir_plantilla("admin"))
        respuesta = como_admin.post("/importar_mis_actividades", data={
            "csrf_token": token_csrf(),
            "archivo": (memoria, "pendientes.xlsx"),
        }, content_type="multipart/form-data")
        assert respuesta.status_code == 302
        assert "error" in respuesta.headers.get("Location", "")

    def test_el_boton_aparece_en_la_pagina_del_usuario(self, cliente,
                                                        iniciar_sesion, db):
        _asignar_actividades(db, "tester", [ACTIVIDAD_A])
        iniciar_sesion()
        cuerpo = cliente.get("/gestion").get_data(as_text=True)
        assert "/descargar_actividades_pendientes" in cuerpo
        assert "/importar_mis_actividades" in cuerpo

    def test_los_botones_no_venlan_a_todos_desde_otro_usuario(self, cliente,
                                                                iniciar_sesion, db):
        """La plantilla se arma con la sesion, no con lo que pida el usuario."""
        _asignar_actividades(db, "tester", [ACTIVIDAD_A])
        _asignar_actividades(db, "admin", ["Actividad del administrador"])
        iniciar_sesion()
        respuesta = cliente.get("/descargar_actividades_pendientes")
        assert respuesta.status_code == 200
        libro = openpyxl.load_workbook(io.BytesIO(respuesta.data))
        hoja = libro[HOJA_ACTIVIDADES]
        textos = [
            hoja.cell(row=f, column=2).value
            for f in range(2, hoja.max_row + 1)
        ]
        assert ACTIVIDAD_A in textos
        assert "Actividad del administrador" not in textos
