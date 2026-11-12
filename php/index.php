<?php
/**
 * Sistema de Actividades - versión PHP para hosting compartido.
 *
 * Todas las direcciones pasan por este archivo:
 *   index.php?ruta=inicio
 *   index.php?ruta=listado&q=texto
 *
 * El archivo config.php tiene los datos de conexión a MySQL.
 */

define('APP_INICIADA', true);

require __DIR__ . '/config.php';
require __DIR__ . '/lib/util.php';
require __DIR__ . '/lib/db.php';
require __DIR__ . '/lib/auth.php';
require __DIR__ . '/lib/excel.php';
require __DIR__ . '/lib/datos.php';
require __DIR__ . '/lib/informe.php';
require __DIR__ . '/lib/tickets.php';
require_once __DIR__ . '/views/layout.php';

cabeceras_seguridad();
iniciar_sesion();

$ruta = isset($_GET['ruta']) ? preg_replace('/[^a-z_]/', '', (string)$_GET['ruta']) : 'inicio';
if ($ruta === '') {
    $ruta = 'inicio';
}

// ---------------------------------------------------------------------------
// Comprobación de salud (para monitoreo; no requiere sesión)
// ---------------------------------------------------------------------------
if ($ruta === 'salud') {
    header('Content-Type: application/json; charset=utf-8');
    try {
        $fila = db_uno("SELECT COUNT(*) AS c FROM registros WHERE COALESCE(borrado, 0) = 0");
        echo json_encode(array(
            'servicio' => 'ok',
            'base_datos' => 'ok',
            'registros' => (int)$fila['c'],
            'version' => 'php',
        ));
    } catch (Exception $error) {
        http_response_code(500);
        echo json_encode(array('servicio' => 'error', 'detalle' => $error->getMessage()));
    }
    exit;
}

// Si la base no está instalada, se envía al instalador.
try {
    db();
} catch (Exception $error) {
    http_response_code(500);
    echo '<!doctype html><html lang="es"><meta charset="utf-8"><body style="font-family:sans-serif;padding:40px">'
        . '<h2>No se pudo conectar con la base de datos</h2>'
        . '<p>' . e($error->getMessage()) . '</p>'
        . '<p>Revise los datos de <code>config.php</code>. Si es la primera vez, abra '
        . '<a href="instalar.php">instalar.php</a>.</p></body></html>';
    exit;
}

if (!db_esta_instalada()) {
    header('Location: instalar.php');
    exit;
}

if (usuario_actual()) {
    validar_sesion();
}

$publicas = array('login', 'inicio_login');
if (!usuario_actual() && !in_array($ruta, array('login'), true)) {
    $error = '';
    if (isset($_GET['error']) && $_GET['error'] !== '') {
        $error = (string)$_GET['error'];
    }
    require __DIR__ . '/views/login.php';
    exit;
}

// Cambio obligatorio de contraseña.
if (usuario_actual()
    && !empty($_SESSION['debe_cambiar'])
    && !in_array($ruta, array('cambiar_contrasena', 'logout'), true)) {
    redirigir('cambiar_contrasena', array('aviso' => 1));
}

// ---------------------------------------------------------------------------
// Acceso y salida
// ---------------------------------------------------------------------------
if ($ruta === 'login') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        redirigir('inicio');
    }
    if (!csrf_ok()) {
        redirigir('inicio', array('error' => 'La sesión expiró. Intente de nuevo.'));
    }

    $ip = ip_cliente();
    if (login_bloqueado($ip)) {
        db_auditar('', 'LOGIN_BLOQUEADO', 'Demasiados intentos desde ' . $ip, $ip);
        redirigir('inicio', array('error' => 'Demasiados intentos fallidos. Espere unos minutos.'));
    }

    $usuario = valor_post('usuario', 50);
    $contrasena = isset($_POST['contrasena']) ? (string)$_POST['contrasena'] : '';

    $fila = db_uno("SELECT * FROM usuarios WHERE username = ?", array($usuario));
    if ($fila && verificar_contrasena($contrasena, $fila['password_hash'], $fila['password_salt'])) {
        registrar_intento_exitoso($ip);
        crear_sesion_usuario($usuario, $ip);
        if (!empty($fila['debe_cambiar_contrasena'])) {
            $_SESSION['debe_cambiar'] = true;
        }
        db_auditar($usuario, 'LOGIN', 'Inicio de sesión', $ip);
        redirigir('inicio');
    }

    registrar_intento_fallido($ip);
    db_auditar($usuario !== '' ? $usuario : '(desconocido)', 'LOGIN_FALLIDO', 'Credenciales incorrectas', $ip);
    redirigir('inicio', array('error' => 'Usuario o contraseña incorrectos'));
}

if ($ruta === 'logout') {
    cerrar_sesion(true);
    redirigir('inicio');
}

requiere_login();

// ---------------------------------------------------------------------------
// Inicio
// ---------------------------------------------------------------------------
if ($ruta === 'inicio') {
    $usuario = usuario_actual();
    $registros = db_cargar_registros(es_admin() ? null : $usuario);
    $registros = ordenar_por_fecha($registros, true);

    $actividades = es_admin() ? array() : db_cargar_actividades($usuario);
    $ubicaciones = db_cargar_lista('ubicacion');
    $tipos_solicitud = db_cargar_lista('tipo_solicitud');
    $medios_solicitud = db_cargar_lista('medio_solicitud');
    $pendientes = es_admin() ? array() : actividades_pendientes($usuario);

    require __DIR__ . '/views/inicio.php';
    exit;
}

// ---------------------------------------------------------------------------
// Registros
// ---------------------------------------------------------------------------
if ($ruta === 'agregar_registro') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('inicio', array('error' => 'Sesión expirada. Intente de nuevo.'));
    }
    $usuario = usuario_actual();
    if (es_admin()) {
        redirigir('inicio', array('error' => 'El administrador no crea registros de actividad'));
    }

    $actividad = valor_post('actividad', 2000);
    $ubicacion = valor_post('ubicacion', 120);
    $tipo = valor_post('tipo_solicitud', 120);
    $medio = valor_post('medio_solicitud', 120);
    $solicitante = valor_post('solicitante', 120);
    if ($actividad === '' || $ubicacion === '' || $tipo === '' || $medio === '' || $solicitante === '') {
        redirigir('inicio', array('error' => 'Complete todos los campos obligatorios'));
    }

    $fecha = fecha_valida(valor_post('fecha_atencion', 10));
    if ($fecha === '') {
        $fecha = hoy();
    }
    $cumplido = valor_post('cumplido', 10);
    if ($cumplido !== 'No') {
        $cumplido = 'Sí';
    }

    try {
        db_guardar_registro(array(
            'usuario' => $usuario,
            'tipo_actividad' => $actividad,
            'fecha' => $fecha . ' ' . hora_actual(),
            'dependencia' => $ubicacion,
            'solicitante' => $solicitante,
            'tipo_solicitud' => $tipo,
            'medio_solicitud' => $medio,
            'descripcion' => valor_post('descripcion', 2000),
            'cumplido' => $cumplido,
            'fecha_atencion' => $fecha,
            'observaciones' => valor_post('observaciones', 1000),
        ));
    } catch (Exception $error) {
        redirigir('inicio', array('error' => 'No se pudo guardar el registro'));
    }

    db_auditar($usuario, 'CREAR_REGISTRO', 'Nueva actividad: ' . $actividad, ip_cliente());
    redirigir('inicio', array('success' => '1'));
}

if ($ruta === 'listado') {
    $usuario = usuario_actual();
    $busqueda = valor_get('q', 100);
    $desde = fecha_valida(valor_get('fecha_inicio', 10));
    $hasta = fecha_valida(valor_get('fecha_fin', 10));
    $estado = valor_get('estado', 10);
    if (!in_array($estado, array('Todos', 'Sí', 'No'), true)) {
        $estado = 'Todos';
    }

    $todos = db_cargar_registros(es_admin() ? null : $usuario);
    $registros = filtrar_registros($todos, $busqueda, $desde, $hasta, $estado);
    $registros = ordenar_por_fecha($registros, true);

    global $CONFIG;
    $por_pagina = (int)$CONFIG['registros_por_pagina'];
    $total_paginas = (int)ceil(count($registros) / $por_pagina);
    if ($total_paginas < 1) {
        $total_paginas = 1;
    }
    $pagina = min(pagina_actual(), $total_paginas);

    require __DIR__ . '/views/listado.php';
    exit;
}

if ($ruta === 'editar_registro') {
    $id = isset($_GET['id_registro']) ? (int)$_GET['id_registro'] : 0;
    $registro = $id > 0 ? db_cargar_registro($id) : null;
    if (!$registro || (!es_admin() && $registro['usuario'] !== usuario_actual())) {
        redirigir('listado', array('error' => 'Registro no encontrado'));
    }

    $usuario = usuario_actual();
    $actividades = db_cargar_actividades($registro['usuario']);
    if (empty($actividades)) {
        $actividades = array($registro['tipo_actividad']);
    }
    $ubicaciones = db_cargar_lista('ubicacion');
    $tipos_solicitud = db_cargar_lista('tipo_solicitud');
    $medios_solicitud = db_cargar_lista('medio_solicitud');

    require __DIR__ . '/views/editar.php';
    exit;
}

if ($ruta === 'actualizar_registro') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('listado', array('error' => 'Sesión expirada. Intente de nuevo.'));
    }
    $id = isset($_POST['id_registro']) ? (int)$_POST['id_registro'] : 0;
    $cumplido = valor_post('cumplido', 10);
    if (!in_array($cumplido, array('Sí', 'No'), true)) {
        redirigir('listado', array('error' => 'Estado de cumplimiento inválido'));
    }

    $datos = array(
        'tipo_actividad' => valor_post('actividad', 2000),
        'dependencia' => valor_post('ubicacion', 120),
        'solicitante' => valor_post('solicitante', 120),
        'tipo_solicitud' => valor_post('tipo_solicitud', 120),
        'medio_solicitud' => valor_post('medio_solicitud', 120),
        'cumplido' => $cumplido,
        'fecha_atencion' => fecha_valida(valor_post('fecha_atencion', 10)),
        'observaciones' => valor_post('observaciones', 1000),
    );
    if (array_key_exists('descripcion', $_POST)) {
        $datos['descripcion'] = valor_post('descripcion', 2000);
    }
    if ($datos['fecha_atencion'] !== '') {
        $datos['fecha'] = $datos['fecha_atencion'] . ' ' . hora_actual();
    }

    if (db_actualizar_registro($id, $datos, usuario_actual())) {
        db_auditar(usuario_actual(), 'ACTUALIZAR_REGISTRO', 'Registro ID ' . $id, ip_cliente());
        redirigir('listado', array('success' => 'actualizado'));
    }
    redirigir('listado', array('error' => 'No se pudo actualizar el registro'));
}

if ($ruta === 'eliminar_registro') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('inicio', array('error' => 'Sesión expirada. Intente de nuevo.'));
    }
    $id = isset($_POST['id_registro']) ? (int)$_POST['id_registro'] : 0;
    if ($id > 0 && db_eliminar_registro($id, usuario_actual())) {
        db_auditar(usuario_actual(), 'ELIMINAR_REGISTRO', 'Registro ID ' . $id, ip_cliente());
        redirigir('inicio', array('deleted' => '1'));
    }
    redirigir('inicio', array('error' => 'Error al eliminar'));
}

// ---------------------------------------------------------------------------
// Importación / exportación de registros
// ---------------------------------------------------------------------------
if ($ruta === 'importar_excel') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('listado', array('error' => 'Sesión expirada. Intente de nuevo.'));
    }
    if (empty($_FILES['archivo']) || $_FILES['archivo']['error'] !== UPLOAD_ERR_OK) {
        redirigir('listado', array('error' => 'Seleccione un archivo Excel'));
    }
    $nombre = isset($_FILES['archivo']['name']) ? strtolower((string)$_FILES['archivo']['name']) : '';
    if (substr($nombre, -5) !== '.xlsx') {
        redirigir('listado', array('error' => 'El archivo debe tener extensión .xlsx'));
    }

    try {
        $filas = ExcelLector::leer($_FILES['archivo']['tmp_name']);
        $lectura = leer_filas_importacion($filas, null);
        $insertados = 0;
        foreach ($lectura['validas'] as $registro) {
            db_guardar_registro($registro);
            $insertados++;
        }
        db_auditar(usuario_actual(), 'IMPORTAR_EXCEL', 'Registros agregados: ' . $insertados, ip_cliente());
        redirigir('listado', array('success' => 'importados_' . $insertados));
    } catch (Exception $error) {
        redirigir('listado', array('error' => 'No se pudo importar el archivo Excel: ' . $error->getMessage()));
    }
}

if ($ruta === 'reemplazar_registros') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('listado', array('error' => 'Sesión expirada. Intente de nuevo.'));
    }
    if (!isset($_POST['confirmacion']) || $_POST['confirmacion'] !== 'REEMPLAZAR_DATOS') {
        redirigir('listado', array('error' => 'Debe escribir REEMPLAZAR_DATOS para confirmar'));
    }
    if (empty($_FILES['archivo']) || $_FILES['archivo']['error'] !== UPLOAD_ERR_OK) {
        redirigir('listado', array('error' => 'Seleccione un archivo Excel'));
    }
    $nombre = isset($_FILES['archivo']['name']) ? strtolower((string)$_FILES['archivo']['name']) : '';
    if (substr($nombre, -5) !== '.xlsx') {
        redirigir('listado', array('error' => 'El archivo debe tener extensión .xlsx'));
    }

    try {
        $filas = ExcelLector::leer($_FILES['archivo']['tmp_name']);
        $lectura = leer_filas_importacion($filas, null);
        if (empty($lectura['validas'])) {
            redirigir('listado', array('error' => 'El archivo no tiene registros válidos'));
        }

        $carpeta = __DIR__ . '/datos/respaldos';
        if (!is_dir($carpeta)) {
            @mkdir($carpeta, 0775, true);
        }
        $nombreRespaldo = 'antes_reemplazo_' . date('Ymd_His') . '.sql';
        @file_put_contents($carpeta . '/' . $nombreRespaldo, respaldo_sql());

        db()->beginTransaction();
        db()->exec('DELETE FROM registros');
        foreach ($lectura['validas'] as $registro) {
            db_guardar_registro($registro);
        }
        db()->commit();

        db_auditar(
            usuario_actual(),
            'REEMPLAZAR_REGISTROS',
            'Total: ' . count($lectura['validas']) . '; respaldo: ' . $nombreRespaldo,
            ip_cliente()
        );
        redirigir('listado', array('success' => 'reemplazados_' . count($lectura['validas'])));
    } catch (Exception $error) {
        if (db()->inTransaction()) {
            db()->rollBack();
        }
        redirigir('listado', array('error' => 'No se pudo reemplazar: ' . $error->getMessage()));
    }
}

if ($ruta === 'descargar_pendientes') {
    try {
        $contenido = excel_pendientes(usuario_actual());
    } catch (Exception $error) {
        redirigir('gestion', array('error' => 'No se pudo generar la plantilla: ' . $error->getMessage()));
    }
    enviar_descarga(
        $contenido,
        'actividades_pendientes_' . usuario_actual() . '_' . date('Ymd') . '.xlsx',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    );
}

if ($ruta === 'importar_mis_actividades') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('inicio', array('error' => 'Sesión expirada. Intente de nuevo.'));
    }
    if (es_admin()) {
        redirigir('inicio', array('error' => 'El administrador no registra actividades'));
    }
    if (empty($_FILES['archivo']) || $_FILES['archivo']['error'] !== UPLOAD_ERR_OK) {
        redirigir('inicio', array('error' => 'Seleccione el archivo de actividades'));
    }
    $nombre = isset($_FILES['archivo']['name']) ? strtolower((string)$_FILES['archivo']['name']) : '';
    if (substr($nombre, -5) !== '.xlsx') {
        redirigir('inicio', array('error' => 'El archivo debe ser .xlsx'));
    }

    try {
        $filas = ExcelLector::leer($_FILES['archivo']['tmp_name']);
        $lectura = leer_pendientes_importadas($filas, usuario_actual());
        if (empty($lectura['validas'])) {
            redirigir('inicio', array('error' => 'No se encontró ningún registro válido. '
                . implode('; ', array_slice($lectura['problemas'], 0, 3))));
        }

        $guardados = 0;
        $errores = array();
        foreach ($lectura['validas'] as $registro) {
            try {
                db_guardar_registro($registro);
                $guardados++;
            } catch (Exception $error) {
                $errores[] = $error->getMessage();
            }
        }
        db_auditar(
            usuario_actual(),
            'IMPORTAR_ACTIVIDADES_PROPIAS',
            'Guardados: ' . $guardados . '; descartadas: ' . $lectura['descartadas'],
            ip_cliente()
        );

        if (!empty($errores)) {
            redirigir('inicio', array('error' => 'Se guardaron ' . $guardados . ' de '
                . count($lectura['validas']) . '. ' . implode('; ', array_slice($errores, 0, 3))));
        }
        if ($lectura['descartadas'] > 0) {
            redirigir('inicio', array('msg' => 'Se guardaron ' . $guardados . ' actividades. '
                . $lectura['descartadas'] . ' fila(s) se descartaron: '
                . implode('; ', array_slice($lectura['problemas'], 0, 3))));
        }
        if ($guardados === 0) {
            redirigir('inicio', array('msg' => 'No había registros nuevos en el archivo'));
        }
        redirigir('inicio', array('success' => 'subidas_' . $guardados));
    } catch (Exception $error) {
        redirigir('inicio', array('error' => 'No se pudo leer el archivo: ' . $error->getMessage()));
    }
}

// ---------------------------------------------------------------------------
// Gestión
// ---------------------------------------------------------------------------
if ($ruta === 'gestion') {
    $usuario = usuario_actual();
    $contrato = db_datos_contrato($usuario);
    if (empty($contrato) && es_admin()) {
        $contrato = db_datos_contrato('admin');
    }
    require __DIR__ . '/views/gestion.php';
    exit;
}

if ($ruta === 'cambiar_contrasena') {
    $usuario = usuario_actual();
    $tiene = usuario_tiene_contrasena($usuario);
    $forzado = !empty($_SESSION['debe_cambiar']);

    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!csrf_ok()) {
            redirigir('cambiar_contrasena', array('error' => 'Sesión expirada. Intente de nuevo.'));
        }
        $nueva = isset($_POST['nueva_contrasena']) ? (string)$_POST['nueva_contrasena'] : '';
        $confirmar = isset($_POST['confirmar_contrasena']) ? (string)$_POST['confirmar_contrasena'] : '';

        if ($tiene && !$forzado) {
            $actual = isset($_POST['contrasena_actual']) ? (string)$_POST['contrasena_actual'] : '';
            $fila = db_uno("SELECT password_hash, password_salt FROM usuarios WHERE username = ?", array($usuario));
            if (!$fila || !verificar_contrasena($actual, $fila['password_hash'], $fila['password_salt'])) {
                db_auditar($usuario, 'CAMBIO_CLAVE_RECHAZADO', 'Contraseña actual incorrecta', ip_cliente());
                redirigir('cambiar_contrasena', array('error' => 'La contraseña actual es incorrecta'));
            }
        }
        if ($nueva !== $confirmar) {
            redirigir('cambiar_contrasena', array('error' => 'Las contraseñas no coinciden'));
        }
        if (largo($nueva) < 6) {
            redirigir('cambiar_contrasena', array('error' => 'La contraseña debe tener al menos 6 caracteres'));
        }

        $tenia = usuario_tiene_contrasena($usuario);
        $resultado = establecer_contrasena($usuario, $nueva, true);
        if (!$resultado[0]) {
            redirigir('cambiar_contrasena', array('error' => $resultado[1]));
        }

        // Cerrar las demás sesiones y conservar esta con un token nuevo.
        revocar_sesiones_usuario($usuario);
        $nuevoToken = bin2hex(random_bytes(32));
        $revision = db_uno("SELECT revision_sesion FROM usuarios WHERE username = ?", array($usuario));
        db_insertar('sesiones', array(
            'token' => $nuevoToken,
            'usuario' => $usuario,
            'revision' => $revision ? (int)$revision['revision_sesion'] : 0,
            'creado' => ahora(),
            'visto' => ahora(),
            'ip' => ip_cliente(),
        ));
        $_SESSION['sesion_token'] = $nuevoToken;

        db_auditar(
            $usuario,
            $tenia ? 'CAMBIO_CONTRASENA' : 'CONTRASENA_INICIAL',
            'Contraseña actualizada',
            ip_cliente()
        );
        db_auditar($usuario, 'SESIONES_REVOCADAS', 'Cierre de otras sesiones', ip_cliente());
        unset($_SESSION['debe_cambiar']);

        if ($forzado) {
            redirigir('inicio', array('msg' => 'Contraseña actualizada. Bienvenido.'));
        }
        redirigir('gestion', array('msg' => 'Contraseña actualizada correctamente'));
    }

    $error = valor_get('error', 300);
    $mensaje = valor_get('msg', 300);
    require __DIR__ . '/views/contrasena.php';
    exit;
}

// ---------------------------------------------------------------------------
// Acciones administrativas de usuarios y catálogos
// ---------------------------------------------------------------------------
if ($ruta === 'agregar_usuario') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }
    $nuevo = valor_post('nuevo_usuario', 50);
    $resultado = crear_usuario($nuevo);
    if ($resultado[0]) {
        db_auditar(usuario_actual(), 'CREAR_USUARIO', 'Nuevo usuario: ' . $nuevo, ip_cliente());
        redirigir('gestion', array('msg' => 'Usuario agregado'));
    }
    redirigir('gestion', array('error' => $resultado[1]));
}

if ($ruta === 'eliminar_usuario') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }
    $objetivo = valor_post('usuario', 50);
    $resultado = eliminar_usuario($objetivo);
    if ($resultado[0]) {
        revocar_sesiones_usuario($objetivo);
        db_auditar(usuario_actual(), 'ELIMINAR_USUARIO', 'Usuario eliminado: ' . $objetivo, ip_cliente());
        redirigir('gestion', array('msg' => 'Usuario eliminado'));
    }
    redirigir('gestion', array('error' => $resultado[1]));
}

if ($ruta === 'asignar_contrasena') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }
    $objetivo = valor_post('usuario', 50);
    $nueva = isset($_POST['nueva_contrasena']) ? (string)$_POST['nueva_contrasena'] : '';
    $forzar = isset($_POST['forzar_cambio']) && $_POST['forzar_cambio'] === '1';

    if (!db_uno("SELECT username FROM usuarios WHERE username = ?", array($objetivo))) {
        redirigir('gestion', array('error' => 'Usuario no encontrado'));
    }
    $resultado = establecer_contrasena($objetivo, $nueva, !$forzar);
    if (!$resultado[0]) {
        redirigir('gestion', array('error' => $resultado[1]));
    }
    if ($forzar) {
        db_ejecutar("UPDATE usuarios SET debe_cambiar_contrasena = 1 WHERE username = ?", array($objetivo));
    }
    db_auditar(
        usuario_actual(),
        'ASIGNAR_CONTRASENA',
        'Contraseña asignada a ' . $objetivo . ($forzar ? ' (requiere cambio)' : ''),
        ip_cliente()
    );
    if ($objetivo !== usuario_actual()) {
        revocar_sesiones_usuario($objetivo);
        db_auditar(usuario_actual(), 'SESIONES_REVOCADAS', 'Sesiones cerradas de ' . $objetivo, ip_cliente());
    }
    redirigir('gestion', array('msg' => 'Contraseña actualizada para ' . $objetivo));
}

if ($ruta === 'guardar_datos_contrato') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }
    $datos = array(
        'nro' => valor_post('nro', 100),
        'objeto' => valor_post('objeto', 500),
        'nombre' => valor_post('nombre', 150),
        'cedula' => valor_post('cedula', 50),
        'supervisor' => valor_post('supervisor', 150),
    );
    try {
        db_guardar_config_usuario(usuario_actual(), 'datos_contrato', $datos);
        db_auditar(usuario_actual(), 'CONFIG_CONTRATO', 'Datos de contrato actualizados', ip_cliente());
        redirigir('gestion', array('msg' => 'Datos de contrato guardados'));
    } catch (Exception $error) {
        redirigir('gestion', array('error' => 'Error al guardar'));
    }
}

$acciones_catalogo = array(
    'agregar_actividad_global' => array('actividad', 'nuevo_item', 'CREAR_ACTIVIDAD_GLOBAL', 'Actividad agregada', 2000),
    'eliminar_actividad_global' => array('actividad', 'actividad', 'ELIMINAR_ACTIVIDAD_GLOBAL', 'Actividad eliminada', 2000),
    'agregar_ubicacion' => array('ubicacion', 'nuevo_item', 'CREAR_UBICACION', 'Ubicación agregada', 120),
    'eliminar_ubicacion' => array('ubicacion', 'ubicacion', 'ELIMINAR_UBICACION', 'Ubicación eliminada', 120),
    'agregar_tipo_solicitud' => array('tipo_solicitud', 'nuevo_item', 'CREAR_TIPO_SOLICITUD', 'Tipo agregado', 120),
    'eliminar_tipo_solicitud' => array('tipo_solicitud', 'tipo', 'ELIMINAR_TIPO_SOLICITUD', 'Tipo eliminado', 120),
    'agregar_medio_solicitud' => array('medio_solicitud', 'nuevo_item', 'CREAR_MEDIO_SOLICITUD', 'Medio agregado', 120),
    'eliminar_medio_solicitud' => array('medio_solicitud', 'medio', 'ELIMINAR_MEDIO_SOLICITUD', 'Medio eliminado', 120),
);
if (isset($acciones_catalogo[$ruta])) {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }
    $accion = $acciones_catalogo[$ruta];
    $valor = valor_post($accion[1], $accion[4]);
    $ok = false;
    if ($valor !== '') {
        if (strpos($ruta, 'agregar_') === 0) {
            $ok = db_guardar_lista($accion[0], $valor);
        } else {
            $ok = db_borrar_lista($accion[0], $valor);
        }
        db_auditar(usuario_actual(), $accion[2], $valor, ip_cliente());
    }
    redirigir('gestion', array('msg' => $accion[3]));
}

if ($ruta === 'agregar_actividad_personal') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }
    $actividad = valor_post('nueva_actividad', 2000);
    if ($actividad === '') {
        redirigir('gestion', array('error' => 'Ingrese una actividad'));
    }
    db_guardar_actividad_personal(usuario_actual(), $actividad);
    redirigir('gestion', array('msg' => 'Actividad personal agregada'));
}

if ($ruta === 'eliminar_actividad_personal') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }
    $actividad = valor_post('actividad', 2000);
    if ($actividad !== '') {
        db_borrar_actividad_personal(usuario_actual(), $actividad);
    }
    redirigir('gestion', array('msg' => 'Actividad personal eliminada'));
}

// ---------------------------------------------------------------------------
// Respaldo
// ---------------------------------------------------------------------------
if ($ruta === 'descargar_respaldo') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }
    try {
        $contenido = respaldo_zip();
        $registros = count(db_cargar_registros());
        db_auditar(
            usuario_actual(),
            'DESCARGAR_RESPALDO',
            'Registros: ' . $registros . '; usuarios: ' . count(db_cargar_usuarios()),
            ip_cliente()
        );
        enviar_descarga(
            $contenido,
            'respaldo_actividades_' . date('Ymd_His') . '.zip',
            'application/zip'
        );
    } catch (Exception $error) {
        redirigir('gestion', array('error' => 'No se pudo generar el respaldo: ' . $error->getMessage()));
    }
}

// ---------------------------------------------------------------------------
// Estadísticas y exportación
// ---------------------------------------------------------------------------
if ($ruta === 'estadisticas') {
    $usuario = usuario_actual();
    $desde = fecha_valida(valor_get('fecha_inicio', 10));
    $hasta = fecha_valida(valor_get('fecha_fin', 10));

    $filas = db_cargar_registros(es_admin() ? null : $usuario);
    $filas = filtrar_registros($filas, '', $desde, $hasta, 'Todos');
    $stats = estadisticas($filas);

    $promedio = '0.0';
    if ($stats['total_registros'] > 0) {
        $base = $desde !== '' ? $desde : $stats['fecha_min'];
        if ($base !== '') {
            $inicio = strtotime($base);
            $fin = $hasta !== '' ? strtotime($hasta) : time();
            $dias = max(1, (int)floor(($fin - $inicio) / 86400) + 1);
            $promedio = number_format($stats['total_registros'] / $dias, 1, '.', '');
        }
    }

    require __DIR__ . '/views/estadisticas.php';
    exit;
}

if ($ruta === 'exportar') {
    $usuario = usuario_actual();

    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        $stats = estadisticas(db_cargar_registros(es_admin() ? null : $usuario));
        $contrato = db_datos_contrato($usuario);
        if (empty($contrato)) {
            $contrato = db_datos_contrato('admin');
        }
        $actividades = es_admin() ? array() : db_cargar_actividades($usuario);
        $usuarios = es_admin() ? db_cargar_usuarios() : array();
        require __DIR__ . '/views/exportar.php';
        exit;
    }

    if (!csrf_ok()) {
        redirigir('exportar', array('error' => 'Sesión expirada. Intente nuevamente.'));
    }

    $desde = fecha_valida(valor_post('fecha_inicio', 10));
    $hasta = fecha_valida(valor_post('fecha_fin', 10));
    $actividad = valor_post('actividad', 2000);
    $formato = valor_post('formato', 10);
    $tipo = valor_post('tipo_reporte', 20);
    $usuarioFiltro = valor_post('usuario_filtro', 50);

    $contrato = array(
        'objeto' => valor_post('contrato_objeto', 500),
        'nro' => valor_post('contrato_nro', 100),
        'nombre' => valor_post('contrato_nombre', 150),
        'cedula' => valor_post('contrato_cedula', 50),
        'supervisor' => valor_post('contrato_supervisor', 150),
    );
    try {
        db_guardar_config_usuario($usuario, 'datos_contrato', $contrato);
    } catch (Exception $error) {
        // Si falla el guardado, la exportación puede continuar.
    }

    if (!es_admin()) {
        $usuarioFiltro = $usuario;
    } elseif ($usuarioFiltro === 'Todos' || $usuarioFiltro === '') {
        $usuarioFiltro = null;
    }

    $filas = db_cargar_registros($usuarioFiltro);
    $filas = filtrar_registros($filas, '', $desde, $hasta, 'Todos');
    if ($actividad !== '') {
        $filas = array_values(array_filter($filas, function ($fila) use ($actividad) {
            return normalizar_texto($fila['tipo_actividad']) === normalizar_texto($actividad);
        }));
    }
    $filas = ordenar_por_fecha($filas, true);

    if (empty($filas)) {
        redirigir('exportar', array('error' => 'No hay datos para exportar'));
    }

    try {
        if ($formato === 'csv') {
            $contenido = csv_exportacion($filas);
            enviar_descarga(
                $contenido,
                'exportacion_' . $usuario . '_' . date('Ymd_His') . '.csv',
                'text/csv; charset=utf-8'
            );
        }
        $contenido = excel_exportacion($filas, $tipo === 'final' ? 'final' : 'detallado', $contrato, $desde, $hasta);
        db_auditar($usuario, 'EXPORTAR', 'Registros: ' . count($filas) . '; tipo: ' . $tipo, ip_cliente());
        enviar_descarga(
            $contenido,
            'Informe_' . ($tipo === 'final' ? 'final' : 'detallado') . '_' . $usuario . '_' . date('Ymd') . '.xlsx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        );
    } catch (Exception $error) {
        redirigir('exportar', array('error' => 'Error al procesar la exportación: ' . $error->getMessage()));
    }
}

// ---------------------------------------------------------------------------
// Auditoría y sesiones
// ---------------------------------------------------------------------------
if ($ruta === 'auditoria') {
    requiere_admin();
    $eventos = db_bitacora(500);
    require __DIR__ . '/views/auditoria.php';
    exit;
}

if ($ruta === 'limpiar_auditoria') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('auditoria', array('error' => 'Sesión expirada'));
    }
    db_limpiar_bitacora(90);
    db_auditar(usuario_actual(), 'LIMPIAR_BITACORA', 'Bitácora limpiada (+90 días)', ip_cliente());
    redirigir('auditoria', array('msg' => 'Bitácora limpiada'));
}

if ($ruta === 'sesiones') {
    requiere_admin();
    $sesiones = sesiones_activas();
    $token_actual = isset($_SESSION['sesion_token']) ? $_SESSION['sesion_token'] : '';
    require __DIR__ . '/views/sesiones.php';
    exit;
}

if ($ruta === 'revocar_sesion') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('sesiones', array('error' => 'Sesión expirada'));
    }
    $token = isset($_POST['token']) ? (string)$_POST['token'] : '';
    if ($token === '') {
        redirigir('sesiones', array('error' => 'Sesión no indicada'));
    }
    $datos = db_uno("SELECT * FROM sesiones WHERE token = ?", array($token));
    revocar_sesion_token($token);
    if ($datos) {
        db_auditar(
            usuario_actual(),
            'REVOCAR_SESION',
            'Sesión cerrada de ' . $datos['usuario'] . ' (' . $datos['ip'] . ')',
            ip_cliente()
        );
    }
    redirigir('sesiones', array('msg' => 'Sesión cerrada'));
}

if ($ruta === 'revocar_todas_sesiones') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('sesiones', array('error' => 'Sesión expirada'));
    }
    db_ejecutar("DELETE FROM sesiones");
    db_ejecutar("UPDATE usuarios SET revision_sesion = COALESCE(revision_sesion, 0) + 1");
    db_auditar(usuario_actual(), 'REVOCAR_TODAS_SESIONES', 'Cierre global de sesiones', ip_cliente());

    $nuevo = bin2hex(random_bytes(32));
    $revision = db_uno("SELECT revision_sesion FROM usuarios WHERE username = ?", array(usuario_actual()));
    db_insertar('sesiones', array(
        'token' => $nuevo,
        'usuario' => usuario_actual(),
        'revision' => $revision ? (int)$revision['revision_sesion'] : 0,
        'creado' => ahora(),
        'visto' => ahora(),
        'ip' => ip_cliente(),
    ));
    $_SESSION['sesion_token'] = $nuevo;
    redirigir('sesiones', array('msg' => 'Todas las sesiones fueron cerradas'));
}

// ---------------------------------------------------------------------------
// Sincronización de usuarios desde JSON
// ---------------------------------------------------------------------------
if ($ruta === 'sincronizar_usuarios') {
    requiere_admin();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('gestion', array('error' => 'Sesión expirada'));
    }

    $rutaJson = null;
    if (!empty($_FILES['archivo']) && $_FILES['archivo']['error'] === UPLOAD_ERR_OK) {
        $nombre = strtolower((string)$_FILES['archivo']['name']);
        if (substr($nombre, -5) !== '.json') {
            redirigir('gestion', array('error' => 'El archivo debe ser un JSON .json'));
        }
        $rutaJson = $_FILES['archivo']['tmp_name'];
    } elseif (is_file(__DIR__ . '/datos/usuarios.json')) {
        $rutaJson = __DIR__ . '/datos/usuarios.json';
    }

    if ($rutaJson === null) {
        redirigir('gestion', array('error' => 'Seleccione el archivo usuarios.json'));
    }

    $datos = json_decode((string)file_get_contents($rutaJson), true);
    if (!is_array($datos)) {
        redirigir('gestion', array('error' => 'El archivo JSON de usuarios no es válido'));
    }

    $nuevos = 0;
    $actividadesAgregadas = 0;
    $configuraciones = 0;
    $listasAgregadas = 0;

    foreach ((array)(isset($datos['usuarios']) ? $datos['usuarios'] : array()) as $cuenta) {
        $cuenta = trim((string)$cuenta);
        if ($cuenta === '') {
            continue;
        }
        if (!db_uno("SELECT username FROM usuarios WHERE username = ?", array($cuenta))) {
            $resultado = crear_usuario($cuenta);
            if ($resultado[0]) {
                $nuevos++;
            }
        }
    }

    $actividades = isset($datos['actividades']) && is_array($datos['actividades']) ? $datos['actividades'] : array();
    foreach ($actividades as $cuenta => $items) {
        if (!is_array($items)) {
            continue;
        }
        foreach ($items as $actividad) {
            if (db_guardar_actividad_personal((string)$cuenta, (string)$actividad)) {
                $actividadesAgregadas++;
            }
        }
    }

    $configuracionesJson = isset($datos['configuraciones']) && is_array($datos['configuraciones'])
        ? $datos['configuraciones'] : array();
    foreach ($configuracionesJson as $cuenta => $config) {
        if (!is_array($config)) {
            continue;
        }
        foreach ($config as $clave => $valor) {
            db_guardar_config_usuario((string)$cuenta, (string)$clave, $valor);
            $configuraciones++;
        }
    }

    $listas = isset($datos['listas_globales']) && is_array($datos['listas_globales'])
        ? $datos['listas_globales']
        : (isset($datos['listas']) && is_array($datos['listas']) ? $datos['listas'] : array());
    foreach ($listas as $tipo => $valores) {
        if (!is_array($valores)) {
            continue;
        }
        foreach ($valores as $valor) {
            if (db_guardar_lista((string)$tipo, (string)$valor)) {
                $listasAgregadas++;
            }
        }
    }

    db_auditar(
        usuario_actual(),
        'SINCRONIZAR_USUARIOS',
        'Usuarios nuevos: ' . $nuevos . '; actividades: ' . $actividadesAgregadas
            . '; configuraciones: ' . $configuraciones . '; listas: ' . $listasAgregadas,
        ip_cliente()
    );
    redirigir('gestion', array('msg' => 'Usuarios y configuraciones sincronizados'));
}


// ---------------------------------------------------------------------------
// Mesa de Ayuda / Gestión de Tickets
// ---------------------------------------------------------------------------
if ($ruta === 'tickets') {
    requiere_login();
    $filtroEstado = isset($_GET['estado']) ? trim((string)$_GET['estado']) : 'Todos';
    $tickets = ticket_listar($filtroEstado, 150);
    $usuarios = db_cargar_usuarios();
    $actividades = db_cargar_actividades(usuario_actual());
    if (empty($actividades)) {
        $actividades = array(
            'Soporte técnico y mantenimiento preventivo/correctivo',
            'Configuración de impresoras, escáneres y periféricos',
            'Soporte y configuración de redes e internet',
            'Gestión de usuarios, contraseñas y permisos de acceso',
            'Instalación y actualización de software y suites de oficina',
            'Atención a requerimientos de infraestructura tecnológica'
        );
    }
    require __DIR__ . '/views/tickets.php';
    exit;
}

if ($ruta === 'ticket_tomar') {
    requiere_login();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('tickets', array('error' => 'Sesión expirada o token inválido'));
    }
    $id = isset($_POST['id']) ? (int)$_POST['id'] : 0;
    if ($id <= 0) {
        redirigir('tickets', array('error' => 'Ticket inválido'));
    }
    if (ticket_tomar($id, usuario_actual())) {
        redirigir('tickets', array('msg' => 'Ha tomado el ticket exitosamente. Ahora está en atención.'));
    } else {
        redirigir('tickets', array('error' => 'No se pudo tomar el ticket'));
    }
}

if ($ruta === 'ticket_resolver') {
    requiere_login();
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !csrf_ok()) {
        redirigir('tickets', array('error' => 'Sesión expirada o token inválido'));
    }
    $id = isset($_POST['id']) ? (int)$_POST['id'] : 0;
    $solucion = isset($_POST['solucion']) ? trim((string)$_POST['solucion']) : '';
    $tipoActividad = isset($_POST['tipo_actividad']) ? trim((string)$_POST['tipo_actividad']) : '';
    $fechaActividad = isset($_POST['fecha_actividad']) ? trim((string)$_POST['fecha_actividad']) : date('Y-m-d');
    $colaboradores = isset($_POST['colaboradores']) && is_array($_POST['colaboradores']) ? $_POST['colaboradores'] : array();

    $res = ticket_resolver($id, usuario_actual(), array(
        'solucion'        => $solucion,
        'tipo_actividad'  => $tipoActividad,
        'fecha_actividad' => $fechaActividad,
        'colaboradores'   => $colaboradores,
    ));

    if ($res[0]) {
        redirigir('tickets', array('msg' => $res[1]));
    } else {
        redirigir('tickets', array('error' => $res[1]));
    }
}

// ---------------------------------------------------------------------------
// Ruta desconocida
// ---------------------------------------------------------------------------
http_response_code(404);
iniciar_pagina('Página no encontrada', '', 'exclamation-triangle');
echo '<div class="alert alert-warning"><h4>Página no encontrada</h4>'
    . '<p>La dirección solicitada no existe.</p>'
    . '<a class="btn btn-primary" href="' . e(url('inicio')) . '">Volver al inicio</a></div>';
terminar_pagina();
