"""Pruebas del respaldo entre Neon y la copia MySQL de 260mb.net."""

from respaldo_service import FORMATO


TOKEN = "token-de-prueba"


def _payload(registros=None, tickets=None, usuarios=None):
    return {
        "formato": FORMATO,
        "confirmar": True,
        "tablas": {
            "usuarios": usuarios or [],
            "registros": registros or [],
            "listas_globales": [],
            "actividades_personales": [],
            "configuracion_usuario": [],
            "tickets": tickets or [],
        },
    }


def _registro(**cambios):
    datos = {
        "id": 900,
        "usuario": "tester",
        "tipo_actividad": "Soporte técnico",
        "fecha": "2026-11-09 08:00:00",
        "dependencia": "OFICINA DE SISTEMAS",
        "solicitante": "Carlos Pérez",
        "tipo_solicitud": "Software",
        "medio_solicitud": "Email",
        "descripcion": "No abre el sistema",
        "cumplido": "Sí",
        "fecha_atencion": "2026-11-09",
        "observaciones": "Se reinstaló",
        "sync_uid": "uid-neon-1",
        "updated_at": "2026-11-09 08:30:00.000000",
        "borrado": 0,
    }
    datos.update(cambios)
    return datos


def _ticket(**cambios):
    datos = {
        "radicado": "TK-202611-0001",
        "dependencia": "OFICINA DE SISTEMAS",
        "solicitante": "Carlos Pérez",
        "correo": "carlos@example.com",
        "telefono": "3001234567",
        "tipo_solicitud": "Software",
        "prioridad": "Alta",
        "descripcion": "No abre el sistema",
        "estado": "Pendiente",
        "tecnico_asignado": None,
        "tecnicos_colaboradores": None,
        "solucion": None,
        "fecha_creacion": "2026-11-09 08:00:00",
        "fecha_atencion": None,
        "fecha_cierre": None,
        "actividades_ids": None,
    }
    datos.update(cambios)
    return datos


def _ejecutar(db, sql, parametros=()):
    with db.db_session() as conn:
        cursor = db.get_cursor(conn)
        cursor.execute(db.fix_query(sql), parametros)


def _consultar(db, sql, parametros=()):
    with db.db_session() as conn:
        cursor = db.get_cursor(conn)
        cursor.execute(db.fix_query(sql), parametros)
        filas = cursor.fetchall()
        resultado = []
        for fila in filas:
            if isinstance(fila, dict):
                resultado.append(tuple(fila.values()))
            else:
                resultado.append(tuple(fila))
        return resultado


def test_exportar_exige_token_configurado(cliente, monkeypatch):
    monkeypatch.delenv("RESPALDO_TOKEN", raising=False)
    respuesta = cliente.get("/respaldo/exportar")
    assert respuesta.status_code == 503


def test_exportar_rechaza_token_incorrecto(cliente, monkeypatch):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    respuesta = cliente.get(
        "/respaldo/exportar", headers={"X-Respaldo-Token": "otro"}
    )
    assert respuesta.status_code == 403


def test_exportar_incluye_las_tablas(cliente, monkeypatch, db):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    db.ticket_crear({
        "dependencia": "OFICINA DE SISTEMAS",
        "solicitante": "Carlos Pérez",
        "tipo_solicitud": "Software",
        "prioridad": "Alta",
        "descripcion": "No abre el sistema",
    })

    respuesta = cliente.get(
        "/respaldo/exportar", headers={"X-Respaldo-Token": TOKEN}
    )

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["formato"] == FORMATO
    assert set(datos["tablas"]) == {
        "usuarios", "registros", "listas_globales",
        "actividades_personales", "configuracion_usuario", "tickets",
    }
    assert len(datos["tablas"]["tickets"]) == 1
    assert datos["conteos"]["tickets"] == 1


def test_exportar_acepta_token_en_la_url(cliente, monkeypatch):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    respuesta = cliente.get("/respaldo/exportar?token=" + TOKEN)
    assert respuesta.status_code == 200


def test_importar_crea_y_actualiza_registros(cliente, monkeypatch, db):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    cabeceras = {"X-Respaldo-Token": TOKEN}

    respuesta = cliente.post(
        "/respaldo/importar", json=_payload(registros=[_registro()]),
        headers=cabeceras,
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["resumen"]["registros"]["insertados"] == 1
    assert _consultar(db, "SELECT COUNT(*) FROM registros")[0][0] == 1

    cambio = _registro(descripcion="No abre el sistema (actualizado)")
    respuesta = cliente.post(
        "/respaldo/importar", json=_payload(registros=[cambio]),
        headers=cabeceras,
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["resumen"]["registros"]["actualizados"] == 1
    filas = _consultar(db, "SELECT descripcion FROM registros")
    assert [f[0] for f in filas] == ["No abre el sistema (actualizado)"]


def test_importar_no_borra_filas_ausentes(cliente, monkeypatch, db, registrar):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    registrar(descripcion="Registro que solo esta en Neon")

    respuesta = cliente.post(
        "/respaldo/importar", json=_payload(),
        headers={"X-Respaldo-Token": TOKEN},
    )

    assert respuesta.status_code == 200
    assert _consultar(db, "SELECT COUNT(*) FROM registros")[0][0] == 1


def test_importar_adopta_fila_por_id_cuando_el_contenido_coincide(
    cliente, monkeypatch, db
):
    """La instalacion PHP genera otro sync_uid, pero conserva el id original."""
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    _ejecutar(
        db,
        """INSERT INTO registros
           (id, usuario, tipo_actividad, fecha, dependencia, solicitante,
            tipo_solicitud, medio_solicitud, descripcion, cumplido,
            fecha_atencion, observaciones, sync_uid, updated_at, borrado)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (900, "tester", "Soporte técnico", "2026-11-09 08:00:00",
         "OFICINA DE SISTEMAS", "Carlos Pérez", "Software", "Email",
         "No abre el sistema", "Sí", "2026-11-09", "Se reinstaló",
         "uid-local-de-260", "2026-11-09 09:00:00", 0),
    )

    respuesta = cliente.post(
        "/respaldo/importar", json=_payload(registros=[_registro()]),
        headers={"X-Respaldo-Token": TOKEN},
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["resumen"]["registros"]["adoptados"] == 1
    filas = _consultar(db, "SELECT id, sync_uid, COUNT(*) FROM registros")
    assert filas[0][0] == 900
    assert filas[0][1] == "uid-neon-1"
    assert filas[0][2] == 1


def test_importar_ticket_nuevo_y_conflicto(cliente, monkeypatch, db):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    cabeceras = {"X-Respaldo-Token": TOKEN}

    respuesta = cliente.post(
        "/respaldo/importar", json=_payload(tickets=[_ticket()]),
        headers=cabeceras,
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["resumen"]["tickets"]["insertados"] == 1

    # Mismo radicado pero otra fecha: son dos tickets distintos. No se toca.
    conflicto = _ticket(fecha_creacion="2026-11-10 08:00:00")
    respuesta = cliente.post(
        "/respaldo/importar", json=_payload(tickets=[conflicto]),
        headers=cabeceras,
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["resumen"]["tickets"]["conflictos"] == 1
    filas = _consultar(db, "SELECT COUNT(*), MIN(fecha_creacion) FROM tickets")
    assert filas[0][0] == 1
    assert filas[0][1] == "2026-11-09 08:00:00"


def test_importar_exige_confirmacion(cliente, monkeypatch):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    datos = _payload()
    datos.pop("confirmar")

    respuesta = cliente.post(
        "/respaldo/importar", json=datos,
        headers={"X-Respaldo-Token": TOKEN},
    )

    assert respuesta.status_code == 400


def test_importar_exige_token(cliente, monkeypatch):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    respuesta = cliente.post("/respaldo/importar", json=_payload())
    assert respuesta.status_code == 403


def test_importar_exige_formato(cliente, monkeypatch):
    monkeypatch.setenv("RESPALDO_TOKEN", TOKEN)
    respuesta = cliente.post(
        "/respaldo/importar",
        json={"confirmar": True, "tablas": {}},
        headers={"X-Respaldo-Token": TOKEN},
    )
    assert respuesta.status_code == 400
