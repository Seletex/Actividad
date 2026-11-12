<?php
/**
 * Respaldo entre Render (Neon) y la copia MySQL de 260mb.net.
 *
 * Uso desde el programador de tareas del hosting (Cron Jobs):
 *
 *     php /home/USUARIO/public_html/respaldo.php
 *
 * Eso trae los datos de Render y los guarda en MySQL. Tambien se puede abrir
 * desde el navegador con el token:
 *
 *     https://su-dominio.260mb.net/respaldo.php?token=EL_TOKEN
 *
 * Acciones:
 *   traer   Copia Render -> MySQL (uso normal, automatico).
 *   enviar  Copia MySQL -> Render (solo despues de una caida real).
 *   estado  Muestra las ultimas sincronizaciones.
 *
 * El token se configura en config.local.php, dentro de 'respaldo'. El mismo
 * valor debe estar en la variable RESPALDO_TOKEN de Render.
 */

define('APP_INICIADA', true);

require __DIR__ . '/config.php';
require __DIR__ . '/lib/util.php';
require __DIR__ . '/lib/db.php';

define('RESPALDO_FORMATO', 'actividades-respaldo-1');
define('RESPALDO_COLUMNAS_REGISTRO', 'usuario, tipo_actividad, fecha, dependencia, solicitante, '
    . 'tipo_solicitud, medio_solicitud, descripcion, cumplido, fecha_atencion, '
    . 'observaciones, sync_uid, updated_at, borrado');

$GLOBALS['respaldo_inicio'] = ahora();

// ---------------------------------------------------------------------------
// Configuracion y utilidades
// ---------------------------------------------------------------------------

function respaldo_config()
{
    global $CONFIG;
    $config = isset($CONFIG['respaldo']) && is_array($CONFIG['respaldo'])
        ? $CONFIG['respaldo']
        : array();

    $urls = array();
    if (!empty($config['url'])) {
        $urls[] = rtrim((string)$config['url'], '/');
    }
    if (!empty($config['urls']) && is_array($config['urls'])) {
        foreach ($config['urls'] as $url) {
            $url = rtrim(trim((string)$url), '/');
            if ($url !== '') {
                $urls[] = $url;
            }
        }
    }

    return array(
        'urls' => array_values(array_unique($urls)),
        'token' => trim((string)(isset($config['token']) ? $config['token'] : '')),
        'timeout' => (int)(isset($config['timeout']) ? $config['timeout'] : 180),
    );
}

function respaldo_es_cli()
{
    return PHP_SAPI === 'cli';
}

function respaldo_token_recibido()
{
    if (isset($_SERVER['HTTP_X_RESPALDO_TOKEN'])) {
        return trim((string)$_SERVER['HTTP_X_RESPALDO_TOKEN']);
    }
    if (isset($_GET['token'])) {
        return trim((string)$_GET['token']);
    }
    if (isset($_POST['token'])) {
        return trim((string)$_POST['token']);
    }
    return '';
}

function respaldo_crear_tabla()
{
    if (db_es_mysql()) {
        db()->exec(
            "CREATE TABLE IF NOT EXISTS sincronizacion (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tipo VARCHAR(20) NOT NULL,
                iniciado VARCHAR(30) DEFAULT NULL,
                terminado VARCHAR(30) DEFAULT NULL,
                estado VARCHAR(20) DEFAULT NULL,
                detalle MEDIUMTEXT,
                KEY idx_sincronizacion_fecha (iniciado)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        );
    } else {
        db()->exec(
            "CREATE TABLE IF NOT EXISTS sincronizacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT,
                iniciado TEXT,
                terminado TEXT,
                estado TEXT,
                detalle TEXT
            )"
        );
    }
}

function respaldo_registrar($tipo, $estado, $resumen)
{
    try {
        db_insertar('sincronizacion', array(
            'tipo' => recortar($tipo, 20),
            'iniciado' => $GLOBALS['respaldo_inicio'],
            'terminado' => ahora(),
            'estado' => recortar($estado, 20),
            'detalle' => json_encode($resumen, JSON_UNESCAPED_UNICODE),
        ));
    } catch (Exception $error) {
        // El registro de la sincronizacion no debe tumbar el respaldo.
    }
}

function respaldo_ultimos($limite = 10)
{
    try {
        $limite = (int)$limite;
        return db_todo("SELECT * FROM sincronizacion ORDER BY id DESC LIMIT " . $limite);
    } catch (Exception $error) {
        return array();
    }
}

function respaldo_json($datos)
{
    $texto = json_encode(
        $datos,
        JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE
    );
    if ($texto === false) {
        throw new RuntimeException('No se pudo preparar el JSON: ' . json_last_error_msg());
    }
    return $texto;
}

function respaldo_http($metodo, $url, $token, $cuerpo = null)
{
    if (!function_exists('curl_init')) {
        throw new RuntimeException('La extension curl de PHP no esta activa en el hosting.');
    }
    $config = respaldo_config();
    $cabeceras = array(
        'Accept: application/json',
        'X-Respaldo-Token: ' . $token,
        'User-Agent: respaldo-260mb/1.0',
    );

    $ch = curl_init($url);
    $opciones = array(
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_MAXREDIRS => 3,
        CURLOPT_CONNECTTIMEOUT => 20,
        CURLOPT_TIMEOUT => max(30, $config['timeout']),
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_ENCODING => '',
    );
    if ($metodo === 'POST') {
        $cabeceras[] = 'Content-Type: application/json';
        $opciones[CURLOPT_POST] = true;
        $opciones[CURLOPT_POSTFIELDS] = $cuerpo;
    }
    $opciones[CURLOPT_HTTPHEADER] = $cabeceras;
    curl_setopt_array($ch, $opciones);

    $respuesta = curl_exec($ch);
    $codigo = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);

    return array($codigo, $respuesta, $error);
}

// ---------------------------------------------------------------------------
// Traer Render -> MySQL
// ---------------------------------------------------------------------------

function respaldo_descargar()
{
    $config = respaldo_config();
    if ($config['token'] === '') {
        throw new RuntimeException(
            'Falta configurar respaldo.token en config.local.php.'
        );
    }
    if (empty($config['urls'])) {
        throw new RuntimeException(
            'Falta configurar respaldo.url en config.local.php.'
        );
    }

    $errores = array();
    foreach ($config['urls'] as $base) {
        $url = $base . '/respaldo/exportar';
        list($codigo, $cuerpo, $error) = respaldo_http('GET', $url, $config['token']);
        if ($codigo === 200 && is_string($cuerpo)) {
            $datos = json_decode($cuerpo, true);
            if (is_array($datos)
                && isset($datos['formato'])
                && $datos['formato'] === RESPALDO_FORMATO
                && isset($datos['tablas'])
            ) {
                return $datos;
            }
            $errores[] = $url . ' respondio, pero el contenido no es un respaldo valido.';
            continue;
        }
        $detalle = $error !== '' ? $error : substr((string)$cuerpo, 0, 300);
        $errores[] = $url . ' -> HTTP ' . $codigo . ' ' . $detalle;
    }

    throw new RuntimeException(
        "No se pudo descargar el respaldo de Render.\n" . implode("\n", $errores)
    );
}

function respaldo_misma_clave($local, $entrante)
{
    $fechaL = substr(str_replace('T', ' ', trim((string)$local['fecha'])), 0, 19);
    $fechaE = substr(str_replace('T', ' ', trim((string)$entrante['fecha'])), 0, 19);
    return trim((string)$local['usuario']) === trim((string)$entrante['usuario'])
        && $fechaL === $fechaE
        && trim((string)$local['descripcion']) === trim((string)$entrante['descripcion']);
}

function respaldo_misma_fecha($a, $b)
{
    $a = substr(str_replace('T', ' ', trim((string)$a)), 0, 19);
    $b = substr(str_replace('T', ' ', trim((string)$b)), 0, 19);
    return $a === '' || $b === '' || $a === $b;
}

function respaldo_busqueda($datos)
{
    return texto_busqueda(array(
        isset($datos['usuario']) ? $datos['usuario'] : '',
        isset($datos['tipo_actividad']) ? $datos['tipo_actividad'] : '',
        isset($datos['fecha']) ? $datos['fecha'] : '',
        isset($datos['dependencia']) ? $datos['dependencia'] : '',
        isset($datos['solicitante']) ? $datos['solicitante'] : '',
        isset($datos['tipo_solicitud']) ? $datos['tipo_solicitud'] : '',
        isset($datos['medio_solicitud']) ? $datos['medio_solicitud'] : '',
        isset($datos['descripcion']) ? $datos['descripcion'] : '',
        isset($datos['cumplido']) ? $datos['cumplido'] : '',
        isset($datos['fecha_atencion']) ? $datos['fecha_atencion'] : '',
        isset($datos['observaciones']) ? $datos['observaciones'] : '',
    ));
}

function respaldo_datos_registro($fila)
{
    $columnas = array(
        'usuario', 'tipo_actividad', 'fecha', 'dependencia', 'solicitante',
        'tipo_solicitud', 'medio_solicitud', 'descripcion', 'cumplido',
        'fecha_atencion', 'observaciones', 'sync_uid', 'updated_at', 'borrado',
    );
    $datos = array();
    foreach ($columnas as $columna) {
        $datos[$columna] = isset($fila[$columna]) ? $fila[$columna] : null;
    }
    $datos['sync_uid'] = trim((string)$datos['sync_uid']);
    if ($datos['sync_uid'] === '') {
        $datos['sync_uid'] = 'legacy-' . (int)(isset($fila['id']) ? $fila['id'] : 0);
    }
    if (empty($datos['updated_at'])) {
        $datos['updated_at'] = ahora();
    }
    $datos['borrado'] = empty($datos['borrado']) ? 0 : 1;
    $datos['busqueda'] = respaldo_busqueda($datos);
    return $datos;
}

function respaldo_actualizar_registro($id, $datos)
{
    $asignaciones = array();
    $parametros = array();
    foreach ($datos as $columna => $valor) {
        $asignaciones[] = '`' . $columna . '` = ?';
        $parametros[] = $valor;
    }
    $parametros[] = (int)$id;
    db_ejecutar(
        'UPDATE registros SET ' . implode(', ', $asignaciones) . ' WHERE id = ?',
        $parametros
    );
}

function respaldo_aplicar($datos)
{
    $tablas = $datos['tablas'];
    $resumen = array(
        'usuarios' => array('insertados' => 0, 'actualizados' => 0),
        'registros' => array('insertados' => 0, 'actualizados' => 0, 'adoptados' => 0),
        'listas_globales' => array('insertadas' => 0),
        'actividades_personales' => array('insertadas' => 0),
        'configuracion_usuario' => array('actualizadas' => 0),
        'tickets' => array('insertados' => 0, 'actualizados' => 0, 'conflictos' => 0),
    );

    // Usuarios
    $existentes = array();
    foreach (db_todo("SELECT username, revision_sesion FROM usuarios") as $fila) {
        $existentes[$fila['username']] = (int)$fila['revision_sesion'];
    }
    foreach ((array)(isset($tablas['usuarios']) ? $tablas['usuarios'] : array()) as $fila) {
        $nombre = trim((string)(isset($fila['username']) ? $fila['username'] : ''));
        if ($nombre === '') {
            continue;
        }
        $revisionEntrante = (int)(isset($fila['revision_sesion']) ? $fila['revision_sesion'] : 0);
        $campos = array(
            'password_hash' => isset($fila['password_hash']) ? $fila['password_hash'] : null,
            'password_salt' => isset($fila['password_salt']) ? $fila['password_salt'] : null,
            'debe_cambiar_contrasena' => !empty($fila['debe_cambiar_contrasena']) ? 1 : 0,
            'revision_sesion' => $revisionEntrante,
        );
        if (isset($existentes[$nombre])) {
            // Nunca bajar la revision: una sesion cerrada no debe revivir.
            $campos['revision_sesion'] = max(
                $existentes[$nombre],
                $revisionEntrante
            );
            if ($campos['password_hash'] === null || $campos['password_hash'] === '') {
                unset($campos['password_hash'], $campos['password_salt']);
            }
            if (!empty($campos)) {
                $asignaciones = array();
                $parametros = array();
                foreach ($campos as $columna => $valor) {
                    $asignaciones[] = '`' . $columna . '` = ?';
                    $parametros[] = $valor;
                }
                $parametros[] = $nombre;
                db_ejecutar(
                    'UPDATE usuarios SET ' . implode(', ', $asignaciones) . ' WHERE username = ?',
                    $parametros
                );
                $resumen['usuarios']['actualizados']++;
            }
        } else {
            db_insertar('usuarios', array_merge(array('username' => $nombre), $campos));
            $resumen['usuarios']['insertados']++;
        }
    }

    // Registros: se conserva el id original para emparejar la primera copia.
    $porUid = array();
    $porId = array();
    foreach (db_todo("SELECT id, sync_uid, usuario, fecha, descripcion FROM registros") as $fila) {
        if (!empty($fila['sync_uid'])) {
            $porUid[$fila['sync_uid']] = $fila;
        }
        $porId[(int)$fila['id']] = $fila;
    }
    $uidsEntrantes = array();
    foreach ((array)(isset($tablas['registros']) ? $tablas['registros'] : array()) as $fila) {
        $uid = trim((string)(isset($fila['sync_uid']) ? $fila['sync_uid'] : ''));
        if ($uid !== '') {
            $uidsEntrantes[$uid] = true;
        }
    }
    foreach ((array)(isset($tablas['registros']) ? $tablas['registros'] : array()) as $fila) {
        $datos = respaldo_datos_registro($fila);
        $uid = $datos['sync_uid'];
        if (isset($porUid[$uid])) {
            respaldo_actualizar_registro((int)$porUid[$uid]['id'], $datos);
            $resumen['registros']['actualizados']++;
            continue;
        }
        $idLocal = (int)(isset($fila['id']) ? $fila['id'] : 0);
        if ($idLocal > 0 && isset($porId[$idLocal])) {
            $local = $porId[$idLocal];
            $uidLocal = trim((string)$local['sync_uid']);
            if (($uidLocal === '' || !isset($uidsEntrantes[$uidLocal]))
                && respaldo_misma_clave($local, $fila)
            ) {
                respaldo_actualizar_registro($idLocal, $datos);
                $resumen['registros']['adoptados']++;
                continue;
            }
        }
        db_insertar('registros', $datos);
        $resumen['registros']['insertados']++;
    }

    // Catalogos: solo se agregan los que faltan.
    $existentes = array();
    foreach (db_todo("SELECT tipo, valor FROM listas_globales") as $fila) {
        $existentes[$fila['tipo'] . "\0" . $fila['valor']] = true;
    }
    foreach ((array)(isset($tablas['listas_globales']) ? $tablas['listas_globales'] : array()) as $fila) {
        $tipo = trim((string)(isset($fila['tipo']) ? $fila['tipo'] : ''));
        $valor = trim((string)(isset($fila['valor']) ? $fila['valor'] : ''));
        $clave = $tipo . "\0" . $valor;
        if ($tipo === '' || $valor === '' || isset($existentes[$clave])) {
            continue;
        }
        db_insertar('listas_globales', array('tipo' => $tipo, 'valor' => $valor));
        $existentes[$clave] = true;
        $resumen['listas_globales']['insertadas']++;
    }

    // Actividades personales: solo se agregan las que faltan.
    $existentes = array();
    foreach (db_todo("SELECT username, actividad FROM actividades_personales") as $fila) {
        $existentes[$fila['username'] . "\0" . $fila['actividad']] = true;
    }
    foreach ((array)(isset($tablas['actividades_personales']) ? $tablas['actividades_personales'] : array()) as $fila) {
        $usuario = trim((string)(isset($fila['username']) ? $fila['username'] : ''));
        $actividad = trim((string)(isset($fila['actividad']) ? $fila['actividad'] : ''));
        $clave = $usuario . "\0" . $actividad;
        if ($usuario === '' || $actividad === '' || isset($existentes[$clave])) {
            continue;
        }
        db_insertar('actividades_personales', array(
            'username' => $usuario,
            'actividad' => $actividad,
        ));
        $existentes[$clave] = true;
        $resumen['actividades_personales']['insertadas']++;
    }

    // Configuracion de usuario.
    foreach ((array)(isset($tablas['configuracion_usuario']) ? $tablas['configuracion_usuario'] : array()) as $fila) {
        $usuario = trim((string)(isset($fila['username']) ? $fila['username'] : ''));
        $clave = trim((string)(isset($fila['clave']) ? $fila['clave'] : ''));
        if ($usuario === '' || $clave === '') {
            continue;
        }
        $valor = isset($fila['valor']) ? (string)$fila['valor'] : '';
        if (db_es_mysql()) {
            db_ejecutar(
                "INSERT INTO configuracion_usuario (username, clave, valor) VALUES (?, ?, ?)
                 ON DUPLICATE KEY UPDATE valor = VALUES(valor)",
                array($usuario, $clave, $valor)
            );
        } else {
            db_ejecutar(
                "INSERT INTO configuracion_usuario (username, clave, valor) VALUES (?, ?, ?)
                 ON CONFLICT(username, clave) DO UPDATE SET valor = excluded.valor",
                array($usuario, $clave, $valor)
            );
        }
        $resumen['configuracion_usuario']['actualizadas']++;
    }

    // Tickets: la llave es el radicado. Si la fecha de creacion no coincide,
    // se trata de dos tickets distintos y no se toca nada.
    $existentes = array();
    foreach (db_todo("SELECT radicado, fecha_creacion FROM tickets") as $fila) {
        $existentes[$fila['radicado']] = $fila;
    }
    $columnasTicket = array(
        'dependencia', 'solicitante', 'correo', 'telefono', 'tipo_solicitud',
        'prioridad', 'descripcion', 'estado', 'tecnico_asignado',
        'tecnicos_colaboradores', 'solucion', 'fecha_creacion',
        'fecha_atencion', 'fecha_cierre', 'actividades_ids',
    );
    foreach ((array)(isset($tablas['tickets']) ? $tablas['tickets'] : array()) as $fila) {
        $radicado = trim((string)(isset($fila['radicado']) ? $fila['radicado'] : ''));
        if ($radicado === '') {
            continue;
        }
        $datos = array();
        foreach ($columnasTicket as $columna) {
            $datos[$columna] = isset($fila[$columna]) ? $fila[$columna] : null;
        }
        if (isset($existentes[$radicado])) {
            if (!respaldo_misma_fecha(
                $existentes[$radicado]['fecha_creacion'],
                isset($fila['fecha_creacion']) ? $fila['fecha_creacion'] : ''
            )) {
                $resumen['tickets']['conflictos']++;
                continue;
            }
            $asignaciones = array();
            $parametros = array();
            foreach ($datos as $columna => $valor) {
                $asignaciones[] = '`' . $columna . '` = ?';
                $parametros[] = $valor;
            }
            $parametros[] = $radicado;
            db_ejecutar(
                'UPDATE tickets SET ' . implode(', ', $asignaciones) . ' WHERE radicado = ?',
                $parametros
            );
            $resumen['tickets']['actualizados']++;
        } else {
            db_insertar('tickets', array_merge(array('radicado' => $radicado), $datos));
            $resumen['tickets']['insertados']++;
        }
    }

    return $resumen;
}

function respaldo_traer()
{
    $datos = respaldo_descargar();
    respaldo_crear_tabla();

    db()->beginTransaction();
    try {
        $resumen = respaldo_aplicar($datos);
        db()->commit();
    } catch (Exception $error) {
        if (db()->inTransaction()) {
            db()->rollBack();
        }
        throw $error;
    }

    respaldo_registrar('traer', 'ok', $resumen);
    return $resumen;
}

// ---------------------------------------------------------------------------
// Enviar MySQL -> Render (solo despues de una caida)
// ---------------------------------------------------------------------------

function respaldo_leer_mysql()
{
    respaldo_crear_tabla();
    $tablas = array(
        'usuarios' => db_todo(
            "SELECT username, password_hash, password_salt,
                    debe_cambiar_contrasena, revision_sesion
             FROM usuarios ORDER BY username"
        ),
        'registros' => db_todo(
            "SELECT id, " . RESPALDO_COLUMNAS_REGISTRO . "
             FROM registros ORDER BY id"
        ),
        'listas_globales' => db_todo(
            "SELECT tipo, valor FROM listas_globales ORDER BY tipo, valor"
        ),
        'actividades_personales' => db_todo(
            "SELECT username, actividad FROM actividades_personales
             ORDER BY username, actividad"
        ),
        'configuracion_usuario' => db_todo(
            "SELECT username, clave, valor FROM configuracion_usuario
             ORDER BY username, clave"
        ),
        'tickets' => db_todo(
            "SELECT radicado, dependencia, solicitante, correo, telefono,
                    tipo_solicitud, prioridad, descripcion, estado,
                    tecnico_asignado, tecnicos_colaboradores, solucion,
                    fecha_creacion, fecha_atencion, fecha_cierre, actividades_ids
             FROM tickets ORDER BY fecha_creacion, radicado"
        ),
    );

    foreach ($tablas['registros'] as $indice => $fila) {
        if (empty($fila['sync_uid'])) {
            $tablas['registros'][$indice]['sync_uid'] =
                'legacy-' . (int)$fila['id'];
        }
    }

    return array(
        'formato' => RESPALDO_FORMATO,
        'generado' => ahora(),
        'confirmar' => true,
        'tablas' => $tablas,
    );
}

function respaldo_enviar()
{
    $config = respaldo_config();
    if ($config['token'] === '') {
        throw new RuntimeException(
            'Falta configurar respaldo.token en config.local.php.'
        );
    }
    if (empty($config['urls'])) {
        throw new RuntimeException(
            'Falta configurar respaldo.url en config.local.php.'
        );
    }

    $datos = respaldo_leer_mysql();
    $cuerpo = respaldo_json($datos);
    $errores = array();

    foreach ($config['urls'] as $base) {
        $url = $base . '/respaldo/importar';
        list($codigo, $respuesta, $error) = respaldo_http(
            'POST', $url, $config['token'], $cuerpo
        );
        $decodificado = is_string($respuesta) ? json_decode($respuesta, true) : null;
        if ($codigo === 200 && is_array($decodificado) && !empty($decodificado['ok'])) {
            $resumen = isset($decodificado['resumen']) ? $decodificado['resumen'] : array();
            respaldo_registrar('enviar', 'ok', $resumen);
            return $resumen;
        }
        $detalle = $error !== '' ? $error : substr((string)$respuesta, 0, 500);
        $errores[] = $url . ' -> HTTP ' . $codigo . ' ' . $detalle;
    }

    throw new RuntimeException(
        "No se pudieron enviar los cambios a Render.\n" . implode("\n", $errores)
    );
}

// ---------------------------------------------------------------------------
// Pantalla del navegador
// ---------------------------------------------------------------------------

function respaldo_pagina($mensaje = '', $esError = false)
{
    $token = respaldo_token_recibido();
    $tokenUrl = rawurlencode($token);
    $config = respaldo_config();
    $ultimos = respaldo_ultimos(10);
    $aviso = isset($_GET['aviso']) ? trim((string)$_GET['aviso']) : '';
    if ($aviso !== '') {
        $mensaje = $aviso;
    }

    header('Content-Type: text/html; charset=utf-8');
    echo '<!doctype html><html lang="es"><head><meta charset="utf-8">';
    echo '<meta name="viewport" content="width=device-width, initial-scale=1">';
    echo '<title>Respaldo 260mb.net</title><style>';
    echo 'body{font-family:Segoe UI,Arial,sans-serif;background:#f4f6f8;color:#1f2933;margin:0;padding:28px}';
    echo '.caja{max-width:920px;margin:0 auto;background:#fff;border-radius:12px;padding:26px 30px;box-shadow:0 2px 14px rgba(0,0,0,.08)}';
    echo 'h1{margin-top:0;font-size:24px}h2{font-size:18px;margin-top:28px}';
    echo '.ok{background:#e6f6ea;border-left:5px solid #2e7d32;padding:12px 16px;margin:16px 0}';
    echo '.mal{background:#fdecea;border-left:5px solid #c62828;padding:12px 16px;margin:16px 0}';
    echo '.nota{background:#fff8e1;border-left:5px solid #f9a825;padding:12px 16px;margin:16px 0}';
    echo 'button{font-size:15px;padding:10px 18px;border:0;border-radius:8px;cursor:pointer;margin:6px 6px 6px 0}';
    echo '.principal{background:#1565c0;color:#fff}.peligro{background:#c62828;color:#fff}';
    echo 'table{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}';
    echo 'th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #e4e7eb;vertical-align:top}';
    echo 'code{background:#eef1f4;padding:2px 5px;border-radius:4px}';
    echo '.estado-ok{color:#2e7d32;font-weight:600}.estado-error{color:#c62828;font-weight:600}';
    echo '</style></head><body><div class="caja">';
    echo '<h1>Respaldo de la mesa de ayuda</h1>';
    echo '<p>Esta copia vive en <strong>260mb.net</strong> y se alimenta de Render. '
        . 'Si Render falla, puede seguir trabajando aquí con los últimos datos recibidos.</p>';

    if ($mensaje !== '') {
        echo '<div class="' . ($esError ? 'mal' : 'ok') . '">' . e($mensaje) . '</div>';
    }

    echo '<div class="nota"><strong>Importante:</strong> el respaldo automático debe '
        . 'traer los datos al menos una vez al día. Si trabajó en esta copia porque '
        . 'Render estuvo caído, primero pulse <strong>Enviar cambios a Render</strong> '
        . 'y solo después vuelva a traer datos.</div>';

    echo '<h2>Traer datos de Render</h2>';
    echo '<p>Copia las actividades, usuarios, catálogos y tickets más recientes.</p>';
    echo '<form method="post" action="respaldo.php?token=' . $tokenUrl . '">';
    echo '<input type="hidden" name="accion" value="traer">';
    echo '<button class="principal" type="submit">Traer datos ahora</button>';
    echo '</form>';

    echo '<h2>Enviar cambios a Render</h2>';
    echo '<p>Use esta opción <strong>solo</strong> si Render estuvo caído y se '
        . 'trabajó en esta copia. Reemplaza en Render las filas que existan en ambos lados.</p>';
    echo '<form method="post" action="respaldo.php?token=' . $tokenUrl . '">';
    echo '<input type="hidden" name="accion" value="enviar">';
    echo '<label><input type="checkbox" name="confirmar" value="1"> '
        . 'Confirmo que Render estuvo caído y que estos son los datos correctos.</label><br>';
    echo '<button class="peligro" type="submit">Enviar cambios a Render</button>';
    echo '</form>';

    echo '<h2>Últimas sincronizaciones</h2>';
    if (empty($ultimos)) {
        echo '<p>Todavía no hay sincronizaciones registradas.</p>';
    } else {
        echo '<table><tr><th>#</th><th>Tipo</th><th>Inicio</th><th>Fin</th>'
            . '<th>Estado</th><th>Detalle</th></tr>';
        foreach ($ultimos as $fila) {
            $clase = $fila['estado'] === 'ok' ? 'estado-ok' : 'estado-error';
            echo '<tr><td>' . (int)$fila['id'] . '</td>'
                . '<td>' . e($fila['tipo']) . '</td>'
                . '<td>' . e($fila['iniciado']) . '</td>'
                . '<td>' . e($fila['terminado']) . '</td>'
                . '<td class="' . $clase . '">' . e($fila['estado']) . '</td>'
                . '<td><code>' . e(recortar((string)$fila['detalle'], 400)) . '</code></td></tr>';
        }
        echo '</table>';
    }

    echo '<h2>Dirección para el programador automático</h2>';
    echo '<p>Si el hosting no tiene Cron Jobs, puede usar un servicio gratuito como '
        . '<code>cron-job.org</code> para abrir esta dirección una vez al día:</p>';
    echo '<p><code>https://' . e(isset($_SERVER['HTTP_HOST']) ? $_SERVER['HTTP_HOST'] : 'su-dominio')
        . '/respaldo.php?token=' . e($token) . '&amp;accion=traer</code></p>';
    echo '<p>El token es una contraseña. No comparta esta dirección.</p>';
    echo '</div></body></html>';
}

// ---------------------------------------------------------------------------
// Programa principal
// ---------------------------------------------------------------------------

$esCli = respaldo_es_cli();
$config = respaldo_config();

if (!$esCli) {
    // En el navegador el token es obligatorio.
    if ($config['token'] === ''
        || !hash_equals($config['token'], respaldo_token_recibido())
    ) {
        http_response_code(403);
        header('Content-Type: text/plain; charset=utf-8');
        exit("Acceso no autorizado. Falta el token o es incorrecto.\n");
    }
}

$accion = 'estado';
$confirmar = false;

if ($esCli) {
    $accion = isset($argv[1]) ? strtolower(trim((string)$argv[1])) : 'traer';
    $confirmar = in_array('--confirmar', $argv, true);
} else {
    if (isset($_POST['accion'])) {
        $accion = strtolower(trim((string)$_POST['accion']));
    } elseif (isset($_GET['accion'])) {
        $accion = strtolower(trim((string)$_GET['accion']));
    }
    $confirmar = isset($_POST['confirmar']) && $_POST['confirmar'] === '1';
}

if (!in_array($accion, array('traer', 'enviar', 'estado'), true)) {
    $accion = 'estado';
}

try {
    if ($accion === 'traer') {
        $resumen = respaldo_traer();
        $mensaje = 'Datos traídos de Render y guardados en MySQL. ' . respaldo_json($resumen);
        if ($esCli) {
            echo $mensaje . "\n";
            exit(0);
        }
        header('Location: respaldo.php?token=' . rawurlencode($config['token'])
            . '&aviso=' . rawurlencode($mensaje));
        exit;
    }

    if ($accion === 'enviar') {
        if (!$confirmar) {
            throw new RuntimeException(
                'Debe marcar la confirmación antes de enviar cambios a Render.'
            );
        }
        $resumen = respaldo_enviar();
        $mensaje = 'Cambios enviados a Render. ' . respaldo_json($resumen);
        if ($esCli) {
            echo $mensaje . "\n";
            exit(0);
        }
        header('Location: respaldo.php?token=' . rawurlencode($config['token'])
            . '&aviso=' . rawurlencode($mensaje));
        exit;
    }

    // estado
    if ($esCli) {
        $ultimos = respaldo_ultimos(10);
        echo "Respaldo 260mb.net\n";
        echo "URL: " . implode(', ', $config['urls']) . "\n";
        echo "Token: " . ($config['token'] !== '' ? 'configurado' : 'FALTA') . "\n";
        if (empty($ultimos)) {
            echo "Sin sincronizaciones registradas.\n";
        } else {
            foreach ($ultimos as $fila) {
                echo sprintf(
                    "#%d %s %s -> %s | %s\n",
                    (int)$fila['id'],
                    $fila['tipo'],
                    $fila['iniciado'],
                    $fila['estado'],
                    recortar((string)$fila['detalle'], 300)
                );
            }
        }
        exit(0);
    }

    respaldo_pagina();
} catch (Exception $error) {
    $mensaje = $error->getMessage();
    respaldo_registrar($accion, 'error', array('error' => $mensaje));
    if ($esCli) {
        fwrite(STDERR, "ERROR: " . $mensaje . "\n");
        exit(1);
    }
    respaldo_pagina($mensaje, true);
}
