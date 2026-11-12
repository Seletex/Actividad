<?php
/**
 * Instalador de la versión PHP.
 *
 * Crea las tablas, carga los catálogos iniciales y el usuario administrador.
 * Si existe datos/datos_iniciales.json (copia de la base actual), también
 * puede cargar esa copia. Al terminar, borre o bloquee este archivo.
 */

define('APP_INICIADA', true);

require __DIR__ . '/config.php';
require __DIR__ . '/lib/util.php';
require __DIR__ . '/lib/db.php';
require __DIR__ . '/lib/auth.php';

cabeceras_seguridad();
iniciar_sesion();

$mensajes = array();
$errores = array();
$instalada = false;

try {
    db();
    $instalada = db_esta_instalada();
} catch (Exception $error) {
    $errores[] = $error->getMessage();
}

$archivoDatos = __DIR__ . '/datos/datos_iniciales.json';
$hayDatos = is_file($archivoDatos);

/**
 * Carga la copia de datos actual sin duplicar lo que ya exista.
 */
function instalar_cargar_datos($ruta)
{
    $datos = json_decode((string)file_get_contents($ruta), true);
    if (!is_array($datos)) {
        throw new RuntimeException('El archivo de datos no es un JSON válido.');
    }

    $resumen = array('usuarios' => 0, 'listas' => 0, 'actividades' => 0, 'configuracion' => 0, 'registros' => 0);

    foreach ((array)(isset($datos['usuarios']) ? $datos['usuarios'] : array()) as $fila) {
        $existe = db_uno("SELECT username, password_hash FROM usuarios WHERE username = ?", array($fila['username']));
        if ($existe) {
            // No se tocan las contraseñas ya establecidas en esta instalación.
            if (empty($existe['password_hash']) && !empty($fila['password_hash'])) {
                db_ejecutar(
                    "UPDATE usuarios SET password_hash = ?, password_salt = ? WHERE username = ?",
                    array($fila['password_hash'], $fila['password_salt'], $fila['username'])
                );
            }
        } else {
            db_insertar('usuarios', array(
                'username' => $fila['username'],
                'password_hash' => $fila['password_hash'],
                'password_salt' => $fila['password_salt'],
                'debe_cambiar_contrasena' => (int)$fila['debe_cambiar_contrasena'],
                'revision_sesion' => (int)$fila['revision_sesion'],
            ));
            $resumen['usuarios']++;
        }
    }

    foreach ((array)(isset($datos['listas_globales']) ? $datos['listas_globales'] : array()) as $fila) {
        if (db_guardar_lista($fila['tipo'], $fila['valor'])) {
            $resumen['listas']++;
        }
    }

    foreach ((array)(isset($datos['actividades_personales']) ? $datos['actividades_personales'] : array()) as $fila) {
        if (db_guardar_actividad_personal($fila['username'], $fila['actividad'])) {
            $resumen['actividades']++;
        }
    }

    foreach ((array)(isset($datos['configuracion_usuario']) ? $datos['configuracion_usuario'] : array()) as $fila) {
        $valor = json_decode($fila['valor'], true);
        if ($valor === null && $fila['valor'] !== 'null') {
            $valor = $fila['valor'];
        }
        db_guardar_config_usuario($fila['username'], $fila['clave'], $valor);
        $resumen['configuracion']++;
    }

    foreach ((array)(isset($datos['registros']) ? $datos['registros'] : array()) as $fila) {
        $registro = array(
            'usuario' => $fila['usuario'],
            'tipo_actividad' => $fila['tipo_actividad'],
            'fecha' => $fila['fecha'],
            'dependencia' => $fila['dependencia'],
            'solicitante' => $fila['solicitante'],
            'tipo_solicitud' => $fila['tipo_solicitud'],
            'medio_solicitud' => $fila['medio_solicitud'],
            'descripcion' => $fila['descripcion'],
            'cumplido' => $fila['cumplido'],
            'fecha_atencion' => $fila['fecha_atencion'],
            'observaciones' => $fila['observaciones'],
            'sync_uid' => bin2hex(random_bytes(16)),
            'updated_at' => ahora(),
            'borrado' => 0,
        );
        // Se conserva el número de registro original para que las referencias
        // del sistema anterior sigan coincidiendo.
        if (!empty($fila['id'])) {
            $registro['id'] = (int)$fila['id'];
        }
        $registro['busqueda'] = !empty($fila['busqueda'])
            ? $fila['busqueda']
            : texto_busqueda(array(
                $registro['usuario'], $registro['tipo_actividad'], $registro['fecha'],
                $registro['dependencia'], $registro['solicitante'], $registro['tipo_solicitud'],
                $registro['medio_solicitud'], $registro['descripcion'], $registro['cumplido'],
                $registro['fecha_atencion'], $registro['observaciones'],
            ));
        db_insertar('registros', $registro);
        $resumen['registros']++;
    }

    return $resumen;
}

// ---------------------------------------------------------------------------
// Procesar la instalación
// ---------------------------------------------------------------------------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && !$instalada) {
    if (!csrf_ok()) {
        $errores[] = 'La página caducó. Vuelva a intentarlo.';
    } else {
        $usuarioAdmin = valor_post('usuario_admin', 50);
        $claveAdmin = isset($_POST['clave_admin']) ? (string)$_POST['clave_admin'] : '';
        if ($usuarioAdmin === '') {
            $usuarioAdmin = 'admin';
        }
        if (largo($claveAdmin) < 6) {
            $errores[] = 'La contraseña del administrador debe tener al menos 6 caracteres.';
        }

        if (empty($errores)) {
            try {
                db_instalar_esquema();
                db_sembrar_catalogos();

                $resultado = crear_usuario($usuarioAdmin, $claveAdmin, 0);
                if (!$resultado[0] && strpos($resultado[1], 'ya existe') === false) {
                    throw new RuntimeException($resultado[1]);
                }

                if ($hayDatos && isset($_POST['cargar_datos'])) {
                    $resumen = instalar_cargar_datos($archivoDatos);
                    $mensajes[] = 'Copia cargada: ' . $resumen['usuarios'] . ' usuario(s) nuevo(s), '
                        . $resumen['listas'] . ' valor(es) de catálogo, '
                        . $resumen['actividades'] . ' actividad(es) personal(es), '
                        . $resumen['configuracion'] . ' configuración(es) y '
                        . $resumen['registros'] . ' registro(s).';
                }

                $instalada = true;
                $mensajes[] = 'Instalación terminada. Ya puede entrar con el usuario '
                    . $usuarioAdmin . '.';
                $mensajes[] = 'Por seguridad, borre o renombre instalar.php cuando termine.';
            } catch (Exception $error) {
                $errores[] = 'No se pudo instalar: ' . $error->getMessage();
            }
        }
    }
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instalar - Sistema de Actividades</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>body { background: #f0f2f5; } .caja { max-width: 720px; margin: 40px auto; }</style>
</head>
<body>
<div class="caja">
    <div class="card">
        <div class="card-header"><h4 class="mb-0">Instalación del Sistema de Actividades (PHP)</h4></div>
        <div class="card-body">
            <?php foreach ($errores as $error): ?>
                <div class="alert alert-danger"><?php echo e($error); ?></div>
            <?php endforeach; ?>
            <?php foreach ($mensajes as $mensaje): ?>
                <div class="alert alert-success"><?php echo e($mensaje); ?></div>
            <?php endforeach; ?>

            <?php if ($instalada): ?>
                <p>La base de datos ya está lista.</p>
                <ul>
                    <li>Entre a <a href="index.php">index.php</a> con el usuario administrador.</li>
                    <li>Si aún no cargó la copia de datos, impórtela con phpMyAdmin usando
                        <code>sql/datos_iniciales.sql</code>.</li>
                    <li>Borre o renombre <code>instalar.php</code> para que nadie más lo use.</li>
                </ul>
                <a class="btn btn-primary" href="index.php">Ir al sistema</a>
            <?php else: ?>
                <p>Se crearán las tablas en la base de datos configurada en <code>config.php</code>.</p>
                <p class="text-muted small">
                    Base actual: <b><?php echo e($CONFIG['db']['driver']); ?></b>
                    <?php if ($CONFIG['db']['driver'] !== 'sqlite'): ?>
                        / <?php echo e($CONFIG['db']['name']); ?> en <?php echo e($CONFIG['db']['host']); ?>
                    <?php endif; ?>
                </p>

                <form method="POST">
                    <?php echo csrf_campo(); ?>
                    <div class="mb-3">
                        <label class="form-label">Usuario administrador</label>
                        <input type="text" name="usuario_admin" class="form-control" value="admin" maxlength="50" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Contraseña del administrador</label>
                        <input type="password" name="clave_admin" class="form-control" minlength="6" required>
                    </div>
                    <?php if ($hayDatos): ?>
                        <div class="form-check mb-3">
                            <input class="form-check-input" type="checkbox" name="cargar_datos" value="1"
                                   id="cargar_datos" checked>
                            <label class="form-check-label" for="cargar_datos">
                                Cargar también la copia de datos actual
                                (<code>datos/datos_iniciales.json</code>)
                            </label>
                        </div>
                    <?php else: ?>
                        <div class="alert alert-info small">
                            No se encontró <code>datos/datos_iniciales.json</code>. Se crearán solo las tablas
                            y los catálogos. Los registros se pueden importar después con phpMyAdmin.
                        </div>
                    <?php endif; ?>
                    <button type="submit" class="btn btn-primary btn-lg">Instalar</button>
                </form>
            <?php endif; ?>
        </div>
    </div>
</div>
</body>
</html>
