"""Pruebas de la comparacion que decide que actividades faltan.

Estas pruebas protegen la regla mas importante de la recuperacion: no volver a
subir lo que ya esta. Un error aqui duplicaria cientos de actividades de una
sola pasada, que es mucho mas dificil de deshacer que de evitar.
"""

from importar_faltantes import clave, faltantes, fecha_para_insertar


def fila(**cambios):
    """Actividad de ejemplo, con los nombres de columna de SQLite/PostgreSQL."""
    datos = {
        "id": 1,
        "usuario": "Manolo",
        "tipo_actividad": "Mantenimiento",
        "fecha": "2026-09-30 10:00:00",
        "dependencia": "ALMACEN",
        "solicitante": "Marcela",
        "tipo_solicitud": "Impresoras",
        "medio_solicitud": "VERBAL",
        "descripcion": "Se revisa la impresora",
        "cumplido": "Sí",
        "fecha_atencion": "2026-09-30",
        "observaciones": "Se revisa la impresora",
    }
    datos.update(cambios)
    return datos


class TestComparacion:
    def test_no_repite_lo_que_ya_esta(self):
        local = fila()
        remoto = fila(id=5000)
        assert faltantes([local], [remoto]) == []

    def test_sube_solo_lo_que_falta(self):
        local = [fila(id=1), fila(id=2, descripcion="Otra cosa",
                                 observaciones="Otra cosa")]
        remoto = [fila(id=5000)]
        resultado = faltantes(local, remoto)
        assert [f["id"] for f in resultado] == [2]

    def test_ignora_mayusculas_tildes_y_espacios(self):
        local = fila(solicitante="JOSÉ   Pérez", descripcion="Revisión  de red")
        remoto = fila(solicitante="jose perez", descripcion="revision de red")
        assert faltantes([local], [remoto]) == []

    def test_respeta_la_cantidad(self):
        """Dos iguales en el equipo y una en la nube: falta una."""
        local = [fila(id=1), fila(id=2)]
        remoto = [fila(id=5000)]
        resultado = faltantes(local, remoto)
        assert len(resultado) == 1

    def test_la_fecha_se_compara_por_dia(self):
        """La hora de creacion no debe hacer parecer distinta la actividad."""
        local = fila(fecha="2026-09-30 15:33:10")
        remoto = fila(fecha="2026-09-30 08:00:00")
        assert faltantes([local], [remoto]) == []

    def test_una_descripcion_distinta_es_otra_actividad(self):
        local = fila(descripcion="Se revisa la impresora")
        remoto = fila(descripcion="Se cambia el toner")
        assert len(faltantes([local], [remoto])) == 1

    def test_excluir_por_id(self):
        local = [fila(id=7), fila(id=8)]
        resultado = faltantes(local, [], excluir={7})
        assert [f["id"] for f in resultado] == [8]


class TestFechaParaInsertar:
    def test_conserva_la_hora_local(self):
        assert fecha_para_insertar(fila(fecha="2026-09-30 15:33:10")) == \
            "2026-09-30 15:33:10"

    def test_si_la_fecha_viene_mal_usa_la_atencion(self):
        assert fecha_para_insertar(
            fila(fecha="", fecha_atencion="2026-10-13")
        ) == "2026-10-13 00:00:00"
