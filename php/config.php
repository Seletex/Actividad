<?php
/**
 * Configuración general de la aplicación.
 *
 * Lo normal es editar este archivo y poner los datos que da el hosting
 * (nombre de la base, usuario y contraseña). Si se prefiere no tocar este
 * archivo, se puede crear config.local.php al lado con los mismos valores.
 */

date_default_timezone_set('America/Bogota');

$CONFIG = array(
    'nombre' => 'Sistema de Actividades',
    'zona_horaria' => 'America/Bogota',

    // 'mysql' en el hosting; 'sqlite' solo para pruebas en un equipo.
    'db' => array(
        'driver' => 'mysql',
        'host' => 'localhost',
        'port' => '3306',
        'name' => 'actividades',
        'user' => 'usuario',
        'pass' => 'clave',
        'sqlite' => __DIR__ . '/datos/actividades.sqlite',
    ),

    // Cantidad de registros por página en el historial.
    'registros_por_pagina' => 50,

    // Respaldo entre Render (Neon) y esta copia en MySQL.
    // El token debe ser el mismo que la variable RESPALDO_TOKEN de Render.
    'respaldo' => array(
        'url' => 'https://actividad-0c88.onrender.com',
        'urls' => array(),
        'token' => '',
        'timeout' => 180,
    ),

    // Bloqueo de acceso tras varios intentos fallidos.
    'max_intentos_login' => 5,
    'minutos_bloqueo' => 15,
);

// Valores locales (no se suben al hosting si se excluye el archivo).
if (is_file(__DIR__ . '/config.local.php')) {
    $local = require __DIR__ . '/config.local.php';
    if (is_array($local)) {
        $CONFIG = array_replace_recursive($CONFIG, $local);
    }
}

// Variables de entorno, útiles para pruebas.
$variables = array(
    'ACT_DB_DRIVER' => array('db', 'driver'),
    'ACT_DB_HOST' => array('db', 'host'),
    'ACT_DB_PORT' => array('db', 'port'),
    'ACT_DB_NAME' => array('db', 'name'),
    'ACT_DB_USER' => array('db', 'user'),
    'ACT_DB_PASS' => array('db', 'pass'),
    'ACT_DB_SQLITE' => array('db', 'sqlite'),
    'ACT_RESPALDO_URL' => array('respaldo', 'url'),
    'ACT_RESPALDO_TOKEN' => array('respaldo', 'token'),
);
foreach ($variables as $nombre => $destino) {
    $valor = getenv($nombre);
    if ($valor !== false && $valor !== '') {
        $CONFIG[$destino[0]][$destino[1]] = $valor;
    }
}

if (!empty($CONFIG['zona_horaria'])) {
    date_default_timezone_set($CONFIG['zona_horaria']);
}
