"""Pruebas de las sesiones activas y su revocacion.

Regresion real que motivo estas pruebas: la sesion de Flask es una cookie
firmada que no se puede cancelar. Cambiar la contrasena, eliminar un usuario o
forzar un cierre no expulsaba a quien ya estaba dentro, y seguian operando
hasta 12 horas.
"""


class TestRegistroDeSesion:
    def test_el_login_registra_la_sesion_en_el_servidor(
        self, iniciar_sesion, db
    ):
        iniciar_sesion()
        assert len(db.listar_sesiones(usuario="tester")) == 1

    def test_dos_equipos_crean_dos_sesiones(self, iniciar_sesion, db):
        iniciar_sesion()
        iniciar_sesion()
        assert len(db.listar_sesiones(usuario="tester")) == 2

    def test_sin_sesion_no_hay_registro(self, db, usuarios):
        assert db.listar_sesiones(usuario="tester") == []


class TestValidacionEnCadaPeticion:
    def test_la_sesion_valida_permite_operar(self, cliente, iniciar_sesion):
        iniciar_sesion()
        assert cliente.get("/gestion").status_code == 200

    def test_un_token_inventado_expulsa_al_usuario(self, cliente, iniciar_sesion):
        """Una cookie manipulada debe rechazarse aunque la firma sea valida."""
        iniciar_sesion()
        with cliente.session_transaction() as sesion:
            sesion["sesion_token"] = "token-falso"
        respuesta = cliente.get("/gestion")
        assert respuesta.status_code == 302
        assert "aviso" in respuesta.headers.get("Location", "")

    def test_sin_token_no_pasa(self, cliente, iniciar_sesion):
        iniciar_sesion()
        with cliente.session_transaction() as sesion:
            sesion.pop("sesion_token", None)
        assert cliente.get("/gestion").status_code == 302


class TestRevocacionPorCambioDeContrasena:
    def test_cambiar_la_clave_cierra_los_otros_equipos(
        self, cliente, otro_cliente, entrar_en, token_de, db
    ):
        """El equipo que cambia la clave sigue dentro; los demas, no."""
        entrar_en(cliente)          # equipo A
        entrar_en(otro_cliente)     # equipo B, mismo usuario, otra cookie
        assert len(db.listar_sesiones(usuario="tester")) == 2

        respuesta = cliente.post("/cambiar_contrasena", data={
            "contrasena_actual": "TesterTemporal123!",
            "nueva_contrasena": "NuevaTemporal456!",
            "confirmar_contrasena": "NuevaTemporal456!",
            "csrf_token": token_de(cliente),
        })
        assert respuesta.status_code == 302

        # El que hizo el cambio conserva el acceso.
        assert cliente.get("/gestion").status_code == 200
        # El otro equipo queda fuera de inmediato.
        respuesta_otro = otro_cliente.get("/gestion")
        assert respuesta_otro.status_code == 302
        assert "aviso" in respuesta_otro.headers.get("Location", "")
        # Y solo queda viva una sesion.
        assert len(db.listar_sesiones(usuario="tester")) == 1

    def test_tras_el_cambio_la_clave_anterior_deja_de_servir(
        self, cliente, otro_cliente, entrar_en, token_de, db
    ):
        """Primero se cambia la clave; despues la anterior debe fallar."""
        entrar_en(cliente)
        cliente.post("/cambiar_contrasena", data={
            "contrasena_actual": "TesterTemporal123!",
            "nueva_contrasena": "NuevaTemporal456!",
            "confirmar_contrasena": "NuevaTemporal456!",
            "csrf_token": token_de(cliente),
        })

        # La clave anterior ya no sirve.
        respuesta = otro_cliente.post("/login", data={
            "usuario": "tester",
            "clave": "TesterTemporal123!",
            "csrf_token": token_de(otro_cliente),
        })
        assert "error" in respuesta.headers.get("Location", "")

        # La nueva si sirve.
        respuesta = otro_cliente.post("/login", data={
            "usuario": "tester",
            "clave": "NuevaTemporal456!",
            "csrf_token": token_de(otro_cliente),
        })
        assert respuesta.status_code == 302
        assert "error" not in respuesta.headers.get("Location", "")


class TestPanelDeSesiones:
    def test_un_usuario_normal_no_accede(self, cliente, iniciar_sesion):
        iniciar_sesion()
        assert cliente.get("/sesiones").status_code == 302

    def test_el_admin_si_accede(self, como_admin):
        assert como_admin.get("/sesiones").status_code == 200

    def test_cerrar_una_sesion_especifica(self, como_admin, token_csrf, db):
        assert db.registrar_sesion("token-a-matar", "tester", "10.0.0.9")
        respuesta = como_admin.post("/revocar_sesion", data={
            "token": "token-a-matar",
            "csrf_token": token_csrf(),
        })
        assert respuesta.status_code == 302
        assert db.sesion_es_valida("token-a-matar", "tester") is False

    def test_cerrar_todas_las_sesiones(self, cliente, otro_cliente, entrar_en,
                                       token_de, db):
        """El cierre global expulsa a todos, incluido el usuario que lo ordena."""
        # El admin cierra desde su propio equipo...
        entrar_en(cliente, "admin", "AdminTemporal123!")
        # ...mientras un usuario normal esta conectado en otro equipo.
        entrar_en(otro_cliente, "tester", "TesterTemporal123!")
        assert db.sesion_es_valida(
            db.listar_sesiones(usuario="tester")[0]["token"], "tester"
        )

        respuesta = cliente.post("/revocar_todas_sesiones", data={
            "csrf_token": token_de(cliente),
        })
        assert respuesta.status_code == 302

        # El usuario normal queda fuera.
        assert otro_cliente.get("/gestion").status_code == 302
        # Y el admin conserva el suyo gracias al token renovado.
        assert cliente.get("/sesiones").status_code == 200

    def test_las_rutas_de_revocacion_exigen_csrf(self, como_admin, db):
        """Sin token, ninguna accion destructiva debe ejecutarse."""
        assert db.registrar_sesion("token-protegido", "tester", "10.0.0.9")

        respuesta = como_admin.post("/revocar_todas_sesiones", data={})
        assert respuesta.status_code in (302, 403)
        # El token sigue vivo: la peticion no llego a ejecutarse.
        assert db.sesion_es_valida("token-protegido", "tester") is True


class TestRevocacionPorBorradoDeUsuario:
    def test_eliminar_un_usuario_cierra_ses_sesiones(self, como_admin,
                                                     token_csrf, db):
        assert db.registrar_sesion("token-del-borrado", "tester", "10.0.0.9")
        como_admin.post("/eliminar_usuario", data={
            "usuario": "tester",
            "csrf_token": token_csrf(),
        })
        assert db.sesion_es_valida("token-del-borrado", "tester") is False


class TestAsignarContrasenaDeOtroUsuario:
    def test_el_admin_que_redefine_una_clave_cierra_sesiones_del_otro(
        self, como_admin, token_csrf, db
    ):
        assert db.registrar_sesion("token-del-borrado", "tester", "10.0.0.9")
        como_admin.post("/asignar_contrasena", data={
            "usuario": "tester",
            "nueva_contrasena": "ClaveNueva789!",
            "csrf_token": token_csrf(),
        })
        assert db.sesion_es_valida("token-del-borrado", "tester") is False
