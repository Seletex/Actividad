"""Pruebas de seguridad de la aplicacion web.

Cubren lo que se corrigio en la revision de seguridad: escape de HTML,
neutralizacion de formules en las exportaciones, cabeceras, cookies y CSRF.
"""


class TestEscapeDeHtml:
    def test_la_tabla_escapa_html_inyectado(self):
        import pandas as pd

        from html_utils import generar_tabla_registros_recientes

        df = pd.DataFrame([{
            "ID": 1,
            "FECHA": "2026-09-30",
            "TIPO DE ACTIVIDAD": "<img src=x onerror=alert(1)>",
            "DEPENDENCIA": "<script>alert(2)</script>",
            "TIPO DE SOLICITUD": "x",
            "CUMPLIDO": "No",
            "USUARIO": "tester",
        }])
        html = generar_tabla_registros_recientes(df, "tester")
        assert "<img" not in html
        assert "&lt;img" in html
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_las_opciones_de_lista_escapan_el_contenido(self):
        from html_utils import generar_opciones_con_seleccion

        html = generar_opciones_con_seleccion(['"><script>evil()</script>'], "")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_el_html_de_una_peticion_real_escapa_el_contenido(self, cliente,
                                                              iniciar_sesion,
                                                              registrar):
        """Un valor con HTML guardado debe salir escapado en el listado."""
        registrar(
            actividad="Actividad <img src=x onerror=alert(1)>",
            solicitante="<script>alert(2)</script>",
        )
        iniciar_sesion()
        respuesta = cliente.get("/listado")
        assert respuesta.status_code == 200
        html = respuesta.get_data(as_text=True)
        assert "<img src=x onerror" not in html
        assert "<script>alert(2)" not in html


class TestFormulasEnExportaciones:
    def test_se_neutralizan_las_formulas(self):
        import pandas as pd

        from export_service import preparar_dataframe_exportable

        df = pd.DataFrame({"SOLICITANTE": ['=HYPERLINK("https://evil")', "normal"]})
        seguro = preparar_dataframe_exportable(df)
        assert seguro.iloc[0]["SOLICITANTE"].startswith("'=")
        assert seguro.iloc[1]["SOLICITANTE"] == "normal"

    def test_tambien_en_mas_signos(self):
        import pandas as pd

        from export_service import preparar_dataframe_exportable

        df = pd.DataFrame({"VALOR": ["+CMD()", "-1+1", "@SUM(A1)"]})
        seguro = preparar_dataframe_exportable(df)
        for valor in seguro["VALOR"]:
            assert valor.startswith("'"), f"deberia neutralizarse: {valor}"

    def test_el_csv_exportado_neutraliza(self, como_admin, token_csrf, registrar):
        registrar(solicitante='=HYPERLINK("https://evil")')
        respuesta = como_admin.post("/exportar", data={
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
            "actividad": "Todas",
            "formato": "csv",
            "tipo_reporte": "detallado",
            "usuario_filtro": "Todos",
            "contrato_objeto": "O",
            "contrato_nro": "1",
            "contrato_nombre": "N",
            "contrato_cedula": "C",
            "contrato_supervisor": "S",
            "csrf_token": token_csrf(),
        })
        assert respuesta.status_code == 200
        # La formula debe aparecer neutralizada, con el apostro inicial.
        assert b"'=HYPERLINK" in respuesta.data


class TestCookieYCabeceras:
    def test_la_cookie_va_cifrada_cuando_se_pide_https(self, cliente, monkeypatch):
        """En produccion (Render) la cookie debe ir marcada como Secure.

        Se prueba sobre una app nueva en vez de la global, para que el resultado
        no dependa de las variables de entorno de quien ejecuta las pruebas.
        """
        from flask import Flask

        import web_security

        monkeypatch.setenv("RENDER", "true")
        monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
        nueva = Flask(__name__)
        web_security.configurar_cookies(nueva)
        assert nueva.config["SESSION_COOKIE_SECURE"] is True
        assert nueva.config["SESSION_COOKIE_HTTPONLY"] is True
        assert nueva.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    def test_la_variable_de_entorno_manda(self, monkeypatch):
        from flask import Flask

        import web_security

        monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
        nueva = Flask(__name__)
        web_security.configurar_cookies(nueva)
        assert nueva.config["SESSION_COOKIE_SECURE"] is True

    def test_sin_render_ni_variable_no_se_marca(self, monkeypatch):
        """En desarrollo local (http) no se marca, para que el flujo funcione."""
        from flask import Flask

        import web_security

        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
        nueva = Flask(__name__)
        web_security.configurar_cookies(nueva)
        assert nueva.config["SESSION_COOKIE_SECURE"] is False

    def test_la_sesion_dura_12_horas(self, monkeypatch):
        from flask import Flask

        import web_security

        nueva = Flask(__name__)
        web_security.configurar_cookies(nueva)
        assert nueva.config["PERMANENT_SESSION_LIFETIME"] == 12 * 60 * 60

    def test_las_cabeceras_de_seguridad_estan(self, cliente):
        respuesta = cliente.get("/", base_url="https://localhost")
        assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
        assert respuesta.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in respuesta.headers
        assert "object-src 'none'" in respuesta.headers["Content-Security-Policy"]

    def test_hsts_solo_sobre_https(self, cliente):
        respuesta = cliente.get("/", base_url="https://localhost")
        assert "max-age=" in respuesta.headers.get("Strict-Transport-Security", "")

    def test_las_paginas_no_se_guardan_en_cache(self, cliente):
        respuesta = cliente.get("/")
        assert "no-store" in respuesta.headers.get("Cache-Control", "")


class TestCsrf:
    def test_el_login_exige_token(self, cliente):
        pagina = cliente.get("/")
        import re
        token = re.search(r'name="csrf_token" value="([^"]+)"',
                          pagina.get_data(as_text=True)).group(1)
        sin_token = cliente.post("/login", data={
            "usuario": "tester", "clave": "TesterTemporal123!",
        })
        con_token = cliente.post("/login", data={
            "usuario": "tester", "clave": "TesterTemporal123!", "csrf_token": token,
        })
        # Sin token no se debe iniciar sesion; con token, si.
        assert "error" in sin_token.headers.get("Location", "")
        assert "error" not in con_token.headers.get("Location", "")

    def test_el_respaldo_solo_se_descarga_con_post(self, como_admin):
        """El respaldo paso de GET a POST: un enlace ya no lo puede descargar."""
        assert como_admin.get("/descargar_respaldo").status_code == 405

    def test_el_respaldo_se_descarga_con_post_y_token(self, como_admin,
                                                       token_csrf):
        respuesta = como_admin.post("/descargar_respaldo", data={
            "csrf_token": token_csrf(),
        })
        assert respuesta.status_code == 200
        assert respuesta.mimetype == "application/zip"


class TestPermisos:
    def test_cada_usuario_tiene_su_propia_gestion(self, cliente, iniciar_sesion):
        """/gestion es personal: cualquier usuario autenticado entra."""
        iniciar_sesion()
        assert cliente.get("/gestion").status_code == 200

    def test_un_usuario_normal_no_entra_a_sesiones(self, cliente,
                                                    iniciar_sesion):
        """Las areas solo de admin si deben quedar fuera."""
        iniciar_sesion()
        assert cliente.get("/sesiones").status_code == 302

    def test_un_usuario_normal_no_administra_usuarios(self, cliente,
                                                      iniciar_sesion,
                                                      token_csrf):
        """No puede crear ni eliminar otros usuarios."""
        iniciar_sesion()
        crear = cliente.post("/agregar_usuario", data={
            "nuevo_usuario": "Intruso",
            "csrf_token": token_csrf(),
        })
        assert crear.status_code == 302
        # En la URL el espacio va codificado como '+'.
        assert "Acceso+denegado" in crear.headers.get("Location", "")

    def test_el_admin_no_crea_registros(self, como_admin, token_csrf):
        """El admin administra; los registros los crean los usuarios."""
        respuesta = como_admin.post("/agregar_registro", data={
            "actividad": "No deberia",
            "fecha_atencion": "2026-10-09",
            "csrf_token": token_csrf(),
        })
        assert "error" in respuesta.headers.get("Location", "")

    def test_sin_sesion_todo_pide_login(self, cliente):
        for ruta in ("/gestion", "/listado", "/estadisticas", "/exportar"):
            assert cliente.get(ruta).status_code == 302, ruta


class TestElRespaldoNoExponeContrasenas:
    def test_el_zip_no_contiene_hashes(self, como_admin, token_csrf, registrar):
        import io
        import zipfile

        registrar()
        respuesta = como_admin.post("/descargar_respaldo", data={
            "csrf_token": token_csrf(),
        })
        assert respuesta.status_code == 200
        with zipfile.ZipFile(io.BytesIO(respuesta.data)) as archivo:
            contenido = b"".join(
                archivo.read(n) for n in archivo.namelist()
            )
        assert b"password_hash" not in contenido
        assert b"password_salt" not in contenido
