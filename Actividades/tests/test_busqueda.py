"""Pruebas del buscador de actividades.

Regresion que motiva estas pruebas: antes el unico filtro era un JavaScript que
recorria las columnas visibles de la tabla. Eso dejaba fuera la descripcion y
las observaciones, que es donde esta escrito el detalle real de la actividad,
y ademas no permitia buscar a los usuarios que tenian cientos de registros.

Ahora la busqueda la resuelve el servidor (parametro ``q`` de ``/listado``) y
recorre todas las columnas de texto. Estas pruebas fijan tres cosas:
- encuentra por descripcion y por observaciones;
- no distingue mayusculas ni tildes, y acepta varias palabras;
- cada usuario solo encuentra lo suyo; el administrador encuentra todo.
"""

import pandas as pd

from app import _filtrar_registros_por_texto


def _df(*filas):
    """DataFrame minimo con las columnas reales de la tabla de registros."""
    return pd.DataFrame(filas)


class TestFiltroDeTexto:
    """Pruebas directas de la funcion que filtra el historial."""

    def test_encuentra_por_descripcion(self):
        df = _df(
            {"TIPO DE ACTIVIDAD": "Mantenimiento", "DESCRIPCIÓN": "Cambio de bomba"},
            {"TIPO DE ACTIVIDAD": "Mantenimiento", "DESCRIPCIÓN": "Pintura"},
        )
        resultado = _filtrar_registros_por_texto(df, "bomba")
        assert list(resultado["DESCRIPCIÓN"]) == ["Cambio de bomba"]

    def test_encuentra_por_observaciones_aunque_la_descripcion_este_vacia(self):
        """Los registros recuperados de Excel traen el detalle en observaciones."""
        df = _df(
            {"TIPO DE ACTIVIDAD": "Apoyo", "DESCRIPCIÓN": "",
             "OBSERVACIONES": "Se atendio en la oficina 302"},
            {"TIPO DE ACTIVIDAD": "Apoyo", "DESCRIPCIÓN": "",
             "OBSERVACIONES": "Sin novedad"},
        )
        resultado = _filtrar_registros_por_texto(df, "oficina 302")
        assert len(resultado) == 1
        assert "oficina 302" in resultado.iloc[0]["OBSERVACIONES"]

    def test_ignora_mayusculas_y_tildes(self):
        df = _df({"DESCRIPCIÓN": "Revisión de señal en el área"})
        assert len(_filtrar_registros_por_texto(df, "REVISION SENAL")) == 1
        assert len(_filtrar_registros_por_texto(df, "revision señal")) == 1

    def test_varias_palabras_deben_aparecer_todas(self):
        df = _df(
            {"DESCRIPCIÓN": "Cambio de bomba", "OBSERVACIONES": "Pozo norte"},
            {"DESCRIPCIÓN": "Cambio de bomba", "OBSERVACIONES": "Pozo sur"},
        )
        assert len(_filtrar_registros_por_texto(df, "bomba norte")) == 1
        assert len(_filtrar_registros_por_texto(df, "bomba occidente")) == 0

    def test_busqueda_vacia_devuelve_todo(self):
        df = _df({"DESCRIPCIÓN": "Uno"}, {"DESCRIPCIÓN": "Dos"})
        assert len(_filtrar_registros_por_texto(df, "")) == 2
        assert len(_filtrar_registros_por_texto(df, "   ")) == 2


class TestBuscadorEnElHistorial:
    """La busqueda funciona a traves de la pagina /listado."""

    def test_encuentra_por_observaciones(self, cliente, iniciar_sesion, registrar):
        registrar(actividad="Revision de equipo",
                  observaciones="Se cambio la bomba del pozo")
        registrar(actividad="Mantenimiento de red",
                  observaciones="Cableado del rack")
        iniciar_sesion()

        pagina = cliente.get("/listado?q=bomba").get_data(as_text=True)

        assert "Revision de equipo" in pagina
        assert "Mantenimiento de red" not in pagina
        assert "1 actividad coincide" in pagina

    def test_acepta_varias_palabras(self, cliente, iniciar_sesion, registrar):
        registrar(actividad="Revision de equipo",
                  observaciones="Se cambio la bomba del pozo")
        registrar(actividad="Mantenimiento de red",
                  observaciones="Cableado del rack")
        iniciar_sesion()

        assert "Revision de equipo" in cliente.get(
            "/listado?q=bomba%20pozo").get_data(as_text=True)
        assert "Revision de equipo" not in cliente.get(
            "/listado?q=bomba%20rack").get_data(as_text=True)

    def test_sin_resultados_lo_dice(self, cliente, iniciar_sesion, registrar):
        registrar(actividad="Revision de equipo")
        iniciar_sesion()

        pagina = cliente.get("/listado?q=inexistente").get_data(as_text=True)

        assert "0 actividades coinciden" in pagina
        assert "Revision de equipo" not in pagina

    def test_la_caja_de_busqueda_conserva_lo_escrito(
        self, cliente, iniciar_sesion, registrar
    ):
        registrar(actividad="Revision de equipo")
        iniciar_sesion()

        pagina = cliente.get("/listado?q=equipo").get_data(as_text=True)

        assert 'name="q"' in pagina
        assert 'value="equipo"' in pagina


class TestAislamientoDeLaBusqueda:
    """Un usuario nunca debe encontrar registros de otro."""

    def test_cada_usuario_solo_encuentra_lo_suyo(
        self, cliente, iniciar_sesion, registrar
    ):
        registrar(usuario="tester", actividad="Actividad de tester",
                  observaciones="dato compartido")
        registrar(usuario="otro", actividad="Actividad de otro",
                  observaciones="dato compartido")
        iniciar_sesion(usuario="tester")

        pagina = cliente.get("/listado?q=compartido").get_data(as_text=True)

        assert "Actividad de tester" in pagina
        assert "Actividad de otro" not in pagina
        assert "1 actividad coincide" in pagina

    def test_el_admin_encuentra_lo_de_todos(self, como_admin, registrar):
        registrar(usuario="tester", actividad="Actividad de tester",
                  observaciones="dato compartido")
        registrar(usuario="otro", actividad="Actividad de otro",
                  observaciones="dato compartido")

        pagina = como_admin.get("/listado?q=compartido").get_data(as_text=True)

        assert "Actividad de tester" in pagina
        assert "Actividad de otro" in pagina
        assert "2 actividades coinciden" in pagina
        assert "Todas las Actividades" in pagina

    def test_el_buscador_de_inicio_lleva_al_historial(
        self, cliente, iniciar_sesion
    ):
        """El buscador visible en la pagina principal apunta al listado."""
        iniciar_sesion()

        pagina = cliente.get("/").get_data(as_text=True)

        assert 'action="/listado"' in pagina
        assert 'name="q"' in pagina
