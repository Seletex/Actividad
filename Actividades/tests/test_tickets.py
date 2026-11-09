"""Pruebas de la mesa de ayuda: radicación, consulta, toma y resolución."""

import re

import pytest


DATOS_TICKET = {
    "dependencia": "OFICINA DE SISTEMAS",
    "solicitante": "Carlos Pérez",
    "correo": "carlos@example.com",
    "telefono": "3001234567",
    "tipo_solicitud": "Impresoras (Configuración / No imprime / Tóner)",
    "prioridad": "Alta",
    "descripcion": "La impresora no imprime desde el equipo de la oficina.",
}


def test_crear_y_consultar_ticket(db):
    ticket = db.ticket_crear(DATOS_TICKET)

    assert ticket["id"] > 0
    assert re.match(r"^TK-\d{6}-\d{4}$", ticket["radicado"])
    assert ticket["estado"] == "Pendiente"

    encontrado = db.ticket_obtener_por_radicado(ticket["radicado"].lower())
    assert encontrado is not None
    assert encontrado["id"] == ticket["id"]
    assert encontrado["solicitante"] == "Carlos Pérez"
    assert encontrado["prioridad"] == "Alta"


def test_prioridad_invalida_se_normaliza(db):
    datos = dict(DATOS_TICKET)
    datos["prioridad"] = "Inventada"
    ticket = db.ticket_crear(datos)
    assert ticket["prioridad"] == "Media"


def test_tomar_ticket(db):
    ticket = db.ticket_crear(DATOS_TICKET)

    assert db.ticket_tomar(ticket["id"], "tester")
    actualizado = db.ticket_obtener_por_id(ticket["id"])
    assert actualizado["estado"] == "En proceso"
    assert actualizado["tecnico_asignado"] == "tester"
    assert actualizado["fecha_atencion"]


def test_resolver_genera_una_actividad_por_tecnico(db):
    ticket = db.ticket_crear(DATOS_TICKET)
    assert db.ticket_tomar(ticket["id"], "tester")

    ok, mensaje = db.ticket_resolver(
        ticket["id"],
        "tester",
        {
            "solucion": "Se cambiaron los controladores y se probó la impresión.",
            "tipo_actividad": "Soporte técnico y mantenimiento",
            "fecha_actividad": "2026-11-09",
            "colaboradores": ["admin", "tester", " admin "],
        },
    )

    assert ok, mensaje
    actualizado = db.ticket_obtener_por_id(ticket["id"])
    assert actualizado["estado"] == "Resuelto"
    assert actualizado["tecnico_asignado"] == "tester"
    assert actualizado["fecha_cierre"]
    assert actualizado["solucion"].startswith("Se cambiaron")
    # "tester" no debe quedar duplicado como colaborador.
    assert actualizado["tecnicos_colaboradores"] == '["admin"]'
    assert len(actualizado["actividades_ids"].split(",")) == 2

    registros = db.cargar_registros(None)
    assert len(registros) == 2
    assert set(registros["USUARIO"]) == {"tester", "admin"}
    assert set(registros["MEDIO DE SOLICITUD"]) == {"Mesa de Ayuda Web"}
    assert set(registros["TIPO DE ACTIVIDAD"]) == {
        "Soporte técnico y mantenimiento"
    }
    assert set(registros["CUMPLIDO"]) == {"Sí"}


def test_resolver_exige_solucion(db):
    ticket = db.ticket_crear(DATOS_TICKET)
    ok, mensaje = db.ticket_resolver(ticket["id"], "tester", {"solucion": "   "})
    assert not ok
    assert "solución" in mensaje.lower()
    assert db.ticket_obtener_por_id(ticket["id"])["estado"] == "Pendiente"


def test_portal_publico_radica_y_consulta(cliente):
    pagina = cliente.get("/ticket")
    assert pagina.status_code == 200
    token = re.search(
        r'name="csrf_token" value="([^"]+)"', pagina.get_data(as_text=True)
    ).group(1)

    respuesta = cliente.post(
        "/ticket",
        data={**DATOS_TICKET, "accion": "crear_ticket", "csrf_token": token},
    )
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert "Solicitud Radicada con Éxito" in html
    radicado = re.search(r"TK-\d{6}-\d{4}", html).group(0)

    consulta = cliente.get("/ticket?radicado=" + radicado)
    assert consulta.status_code == 200
    texto = consulta.get_data(as_text=True)
    assert radicado in texto
    assert "Pendiente" in texto
    assert "Carlos Pérez" in texto


def test_portal_publico_exige_campos(cliente):
    pagina = cliente.get("/ticket")
    token = re.search(
        r'name="csrf_token" value="([^"]+)"', pagina.get_data(as_text=True)
    ).group(1)
    respuesta = cliente.post(
        "/ticket",
        data={"accion": "crear_ticket", "csrf_token": token, "solicitante": ""},
    )
    assert respuesta.status_code == 200
    assert "complete todos los campos obligatorios" in respuesta.get_data(
        as_text=True
    )


def test_bandeja_requiere_login(cliente):
    respuesta = cliente.get("/tickets")
    assert respuesta.status_code == 302


def test_bandeja_muestra_ticket(cliente, iniciar_sesion, db):
    ticket = db.ticket_crear(DATOS_TICKET)
    iniciar_sesion()

    respuesta = cliente.get("/tickets")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert ticket["radicado"] in html
    assert "Mesa de Ayuda" in html
    assert "Carlos Pérez" in html


def test_tomar_ticket_desde_bandeja(cliente, iniciar_sesion, token_csrf, db):
    ticket = db.ticket_crear(DATOS_TICKET)
    iniciar_sesion()

    respuesta = cliente.post(
        "/ticket_tomar",
        data={"id": ticket["id"], "csrf_token": token_csrf()},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    actualizado = db.ticket_obtener_por_id(ticket["id"])
    assert actualizado["estado"] == "En proceso"
    assert actualizado["tecnico_asignado"] == "tester"


def test_resolver_desde_bandeja(cliente, iniciar_sesion, token_csrf, db):
    ticket = db.ticket_crear(DATOS_TICKET)
    assert db.ticket_tomar(ticket["id"], "tester")
    iniciar_sesion()

    respuesta = cliente.post(
        "/ticket_resolver",
        data={
            "id": ticket["id"],
            "solucion": "Se reinstaló el controlador de impresión.",
            "tipo_actividad": "Soporte técnico y mantenimiento",
            "fecha_actividad": "2026-11-09",
            "colaboradores": ["admin"],
            "csrf_token": token_csrf(),
        },
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    actualizado = db.ticket_obtener_por_id(ticket["id"])
    assert actualizado["estado"] == "Resuelto"
    registros = db.cargar_registros(None)
    assert set(registros["USUARIO"]) == {"tester", "admin"}


def test_no_se_puede_tomar_ni_resolver_dos_veces(db):
    ticket = db.ticket_crear(DATOS_TICKET)
    assert db.ticket_tomar(ticket["id"], "tester")
    ok, _ = db.ticket_resolver(
        ticket["id"],
        "tester",
        {
            "solucion": "Se solucionó el inconveniente.",
            "tipo_actividad": "Soporte técnico y mantenimiento",
            "fecha_actividad": "2026-11-09",
        },
    )
    assert ok

    # Un ticket cerrado no se reabre ni genera actividades duplicadas.
    assert not db.ticket_tomar(ticket["id"], "admin")
    ok, mensaje = db.ticket_resolver(
        ticket["id"],
        "admin",
        {
            "solucion": "Otro cierre.",
            "tipo_actividad": "Soporte técnico y mantenimiento",
            "fecha_actividad": "2026-11-09",
        },
    )
    assert not ok
    assert "resuelto" in mensaje.lower()
    assert len(db.cargar_registros(None)) == 1


def test_tomar_sin_csrf_no_cambia_el_ticket(cliente, iniciar_sesion, db):
    ticket = db.ticket_crear(DATOS_TICKET)
    iniciar_sesion()

    respuesta = cliente.post(
        "/ticket_tomar", data={"id": ticket["id"]}, follow_redirects=True
    )
    assert respuesta.status_code == 200
    assert db.ticket_obtener_por_id(ticket["id"])["estado"] == "Pendiente"
