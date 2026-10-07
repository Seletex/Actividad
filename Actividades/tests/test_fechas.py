"""Pruebas del manejo de fechas y de los filtros por rango.

Regresiones que motivan estas pruebas:
- Al editar un registro se actualizaba solo FECHA ATENCION; FECHA (fecha de
  solicitud) conservaba el valor viejo y quedaban dos fechas distintas.
- Los filtros de los reportes se aplicaban sobre la fecha de solicitud en vez
  de la fecha en que se atendio la actividad.
- El rango de fechas desaparecio del encabezado de los Excel porque la columna
  auxiliar del filtro se eliminaba antes de generar el archivo.
"""

import re
import zipfile
from io import BytesIO

from export_service import (
    _rango_fechas_texto,
    exportar_registros_filtrados,
)
from tests.conftest import consultar, ejecutar

PATRON_RANGO = re.compile(r"\d{2}/\d{2}/\d{4}\s*al\s*\d{2}/\d{2}/\d{4}")


class TestAltaDeRegistro:
    def test_el_alta_escribe_las_dos_fechas_iguales(self, cliente, iniciar_sesion,
                                                    token_csrf, db):
        iniciar_sesion()
        respuesta = cliente.post("/agregar_registro", data={
            "actividad": "Actividad nueva",
            "ubicacion": "Dependencia",
            "tipo_solicitud": "Asistencia",
            "medio_solicitud": "Email",
            "solicitante": "Solicitante",
            "cumplido": "Sí",
            "fecha_atencion": "2026-10-09",
            "descripcion": "Descripcion",
            "observaciones": "Observaciones",
            "csrf_token": token_csrf(),
        })
        assert respuesta.status_code == 302

        filas = consultar(db, "SELECT fecha, fecha_atencion FROM registros"
                          " WHERE tipo_actividad = ?", ("Actividad nueva",))
        assert filas, "el registro deberia haberse guardado"
        fecha, fecha_atencion = filas[0]

        assert fecha_atencion == "2026-10-09"
        assert str(fecha).startswith("2026-10-09"), \
            f"FECHA debe acompanar a la atencion, no {fecha}"

    def test_una_fecha_invalida_no_se_acepta_como_atencion(self, db):
        """La fecha se normaliza; un valor imposible se descarta."""
        from app import _fecha_valida

        assert _fecha_valida("2026-10-09") == "2026-10-09"
        assert _fecha_valida("09/10/2026") == ""
        assert _fecha_valida("no-es-fecha") == ""
        assert _fecha_valida("") == ""


class TestEdicionDeRegistro:
    def test_editar_alinea_las_dos_fechas(self, cliente, iniciar_sesion,
                                          token_csrf, registrar, db):
        """Al editar, FECHA debe seguir a FECHA ATENCION."""
        registrar(fecha="2026-09-20 08:00:00", fecha_atencion="2026-09-25")

        filas = consultar(db, "SELECT id FROM registros")
        assert filas, "no se registro la actividad de prueba"
        id_registro = filas[0][0]

        iniciar_sesion()
        respuesta = cliente.post("/actualizar_registro_accion", data={
            "id_registro": str(id_registro),
            "actividad": "Actividad de prueba",
            "ubicacion": "Dependencia",
            "solicitante": "Solicitante",
            "tipo_solicitud": "Asistencia",
            "medio_solicitud": "Email",
            "cumplido": "Sí",
            "fecha_atencion": "2026-10-05",
            "observaciones": "Observaciones",
            "csrf_token": token_csrf(),
        })

        resultado = consultar(db, "SELECT fecha, fecha_atencion FROM registros"
                              " WHERE id = ?", (id_registro,))
        fecha, fecha_atencion = resultado[0]

        # Si el guardado no ocurrio, el aviso lo dira claro.
        assert "error" not in respuesta.headers.get("Location", ""), \
            f"la edicion fue rechazada: {respuesta.headers.get('Location')}"

        assert fecha_atencion == "2026-10-05"
        assert str(fecha).startswith("2026-10-05"), \
            f"tras editar, ambas fechas deben coincidir: {fecha}"

    def test_la_hora_se_actualiza_al_editar(self, cliente, iniciar_sesion,
                                            token_csrf, registrar, db):
        """Al editar, FECHA queda con la fecha de atencion y la hora del momento.

        Comportamiento documentado a proposito: la parte de la fecha sigue a la
        fecha de atencion (que es lo pedido) y la hora es la del instante en que
        se guardo el cambio.
        """
        registrar(fecha="2026-09-20 08:30:45", fecha_atencion="2026-09-25")

        filas = consultar(db, "SELECT id FROM registros")
        id_registro = filas[0][0]

        iniciar_sesion()
        respuesta = cliente.post("/actualizar_registro_accion", data={
            "id_registro": str(id_registro),
            "actividad": "Actividad de prueba",
            "ubicacion": "Dependencia",
            "solicitante": "Solicitante",
            "tipo_solicitud": "Asistencia",
            "medio_solicitud": "Email",
            "cumplido": "Sí",
            "fecha_atencion": "2026-10-05",
            "observaciones": "Observaciones",
            "csrf_token": token_csrf(),
        })

        resultado = consultar(db, "SELECT fecha, fecha_atencion FROM registros"
                              " WHERE id = ?", (id_registro,))
        fecha, fecha_atencion = resultado[0]
        fecha = str(fecha)

        assert "error" not in respuesta.headers.get("Location", ""), \
            f"la edicion fue rechazada: {respuesta.headers.get('Location')}"

        assert fecha_atencion == "2026-10-05"
        assert fecha[:10] == "2026-10-05"
        # La hora debe tener formato HH:MM:SS y ser la del guardado, no la vieja.
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", fecha)
        assert not fecha.endswith("08:30:45"), \
            "la hora debe ser la del momento de editar, no la original"


class TestFiltroPorFechaDeAtencion:
    def test_el_filtro_usa_la_fecha_de_atencion(self, registrar):
        """Un registro con fechas distintas demuestra que columna manda."""
        registrar(actividad="A", fecha="2026-09-01 08:00:00",
                  fecha_atencion="2026-09-15")
        registrar(actividad="B", fecha="2026-09-20 08:00:00",
                  fecha_atencion="2026-09-25")

        df, _ = exportar_registros_filtrados(
            fecha_inicio="2026-09-10", fecha_fin="2026-09-20"
        )
        assert sorted(df["TIPO DE ACTIVIDAD"].tolist()) == ["A"], \
            "en 10-20 solo entra la actividad atendida el 15"

    def test_no_se_filtra_por_la_fecha_de_solicitud(self, registrar):
        """El dia 20 no debe traer nada: esa actividad se atendio el 25."""
        registrar(actividad="A", fecha="2026-09-01 08:00:00",
                  fecha_atencion="2026-09-15")
        registrar(actividad="B", fecha="2026-09-20 08:00:00",
                  fecha_atencion="2026-09-25")

        df, _ = exportar_registros_filtrados(
            fecha_inicio="2026-09-20", fecha_fin="2026-09-20"
        )
        assert df.empty, "filtrar por atencion no debe traer B en el dia 20"

    def test_el_rango_final_es_inclusivo(self, registrar):
        registrar(actividad="A", fecha_atencion="2026-09-15")
        df, _ = exportar_registros_filtrados(
            fecha_inicio="2026-09-15", fecha_fin="2026-09-15"
        )
        assert sorted(df["TIPO DE ACTIVIDAD"].tolist()) == ["A"], \
            "el dia final debe incluir todo el dia"

    def test_sin_atencion_se_usa_la_fecha_de_solicitud(self, db):
        """Si falta la fecha de atencion, el registro no debe desaparecer."""
        ejecutar(db,
            """INSERT INTO registros
               (usuario, tipo_actividad, fecha, dependencia, solicitante,
                tipo_solicitud, medio_solicitud, descripcion, cumplido,
                fecha_atencion, observaciones, borrado)
               VALUES ('tester','Sin atencion','2026-09-12 08:00:00','D','S',
                       'A','E','D','Sí','','O',0)"""
        )
        df, _ = exportar_registros_filtrados(
            fecha_inicio="2026-09-10", fecha_fin="2026-09-20"
        )
        assert "Sin atencion" in df["TIPO DE ACTIVIDAD"].tolist()

    def test_el_listado_filtra_por_atencion(self, cliente, iniciar_sesion,
                                            registrar):
        registrar(actividad="ActividadAlfa", fecha="2026-09-01 08:00:00",
                  fecha_atencion="2026-09-15")
        registrar(actividad="ActividadBeta", fecha="2026-09-20 08:00:00",
                  fecha_atencion="2026-09-25")

        iniciar_sesion()
        respuesta = cliente.get("/listado?fecha_inicio=2026-09-10"
                                "&fecha_fin=2026-09-20")
        assert respuesta.status_code == 200
        cuerpo = respuesta.get_data(as_text=True)
        assert "ActividadAlfa" in cuerpo, "la actividad atendida el 15 debe salir"
        assert "ActividadBeta" not in cuerpo, \
            "la actividad atendida el 25 no debe salir en el rango 10-20"


class TestRangoDeFechasEnLosInformes:
    def test_el_rango_se_calcula_sin_la_columna_auxiliar(self, registrar):
        """Regresion: quitar la columna interna dejaba el rango vacio."""
        registrar(actividad="A", fecha_atencion="2026-09-10")
        registrar(actividad="B", fecha_atencion="2026-09-25")

        df, _ = exportar_registros_filtrados(
            fecha_inicio="2026-09-01", fecha_fin="2026-09-30"
        )
        sin_auxiliar = df.drop(columns=["_FECHA_FILTRO"], errors="ignore")

        assert _rango_fechas_texto(df) == "10/09/2026 al 25/09/2026"
        assert _rango_fechas_texto(sin_auxiliar) == "10/09/2026 al 25/09/2026", \
            "el rango debe calcularse aun sin la columna auxiliar"

    def test_el_excel_trae_el_rango_y_no_la_columna_interna(
        self, cliente, como_admin, token_csrf, registrar
    ):
        registrar(actividad="A", fecha_atencion="2026-09-10")
        registrar(actividad="B", fecha_atencion="2026-09-25")

        respuesta = como_admin.post("/exportar", data={
            "fecha_inicio": "2026-09-01",
            "fecha_fin": "2026-09-30",
            "actividad": "Todas",
            "formato": "excel",
            "tipo_reporte": "detallado",
            "usuario_filtro": "Todos",
            "contrato_objeto": "OBJ",
            "contrato_nro": "1",
            "contrato_nombre": "N",
            "contrato_cedula": "C",
            "contrato_supervisor": "S",
            "csrf_token": token_csrf(),
        })
        assert respuesta.status_code == 200

        # Un xlsx es un zip: hay que buscar el texto dentro de sus hojas.
        with zipfile.ZipFile(BytesIO(respuesta.data)) as archivo:
            contenido = "".join(
                archivo.read(n).decode("utf-8", errors="replace")
                for n in archivo.namelist()
                if n.startswith("xl/")
            )
        assert PATRON_RANGO.search(contenido), \
            "el Excel debe indicar el rango de fechas del informe"
        assert "_FECHA_FILTRO" not in contenido, \
            "la columna interna no debe aparecer en el Excel"

    def test_el_csv_no_lleva_la_columna_interna(self, como_admin, token_csrf,
                                               registrar):
        registrar(actividad="A", fecha_atencion="2026-09-10")

        respuesta = como_admin.post("/exportar", data={
            "fecha_inicio": "2026-09-01",
            "fecha_fin": "2026-09-30",
            "actividad": "Todas",
            "formato": "csv",
            "tipo_reporte": "detallado",
            "usuario_filtro": "Todos",
            "contrato_objeto": "OBJ",
            "contrato_nro": "1",
            "contrato_nombre": "N",
            "contrato_cedula": "C",
            "contrato_supervisor": "S",
            "csrf_token": token_csrf(),
        })
        assert respuesta.status_code == 200
        assert b"_FECHA_FILTRO" not in respuesta.data
