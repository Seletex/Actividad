<?php
/**
 * Bitácora de auditoría (solo administrador).
 *
 * @var array $eventos
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

iniciar_pagina('Auditoría', 'auditoria', 'clipboard-list');

$iconos = array(
    'LOGIN' => '🟢', 'LOGIN_FALLIDO' => '🔴', 'LOGIN_BLOQUEADO' => '⛔',
    'LOGOUT' => '⚪', 'CAMBIO_CONTRASENA' => '🔑', 'CONTRASENA_INICIAL' => '🔑',
    'CAMBIO_CLAVE_RECHAZADO' => '🔒', 'ELIMINAR_REGISTRO' => '🗑️',
    'CREAR_USUARIO' => '➕', 'ELIMINAR_USUARIO' => '➖',
    'CREAR_UBICACION' => '📍', 'ELIMINAR_UBICACION' => '❌',
    'CONFIG_CONTRATO' => '📄', 'LIMPIAR_BITACORA' => '🧹',
);
?>

<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
    <h2 class="mb-0"><i class="fas fa-clipboard-list"></i> Auditoría</h2>
    <div class="d-flex gap-2">
        <a href="<?php echo e(url('gestion')); ?>" class="btn btn-outline-secondary btn-sm">
            <i class="fas fa-arrow-left"></i> Volver
        </a>
        <form action="<?php echo e(url('limpiar_auditoria')); ?>" method="POST"
              onsubmit="return confirm('¿Borrar los eventos de auditoría de más de 90 días?')">
            <?php echo csrf_campo(); ?>
            <button class="btn btn-outline-danger btn-sm"><i class="fas fa-broom"></i> Limpiar (+90 días)</button>
        </form>
    </div>
</div>

<p class="text-muted small">
    Se muestran los últimos 500 eventos. La auditoría registra accesos, cambios de contraseña,
    altas y bajas de usuarios y eliminación de registros.
</p>

<div class="card">
    <div class="card-body p-0">
        <div class="table-responsive">
            <table class="table table-sm align-middle mb-0">
                <thead class="table-light">
                    <tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Detalle</th><th>IP</th></tr>
                </thead>
                <tbody>
                <?php if (empty($eventos)): ?>
                    <tr><td colspan="5" class="text-center text-muted py-4">No hay eventos registrados</td></tr>
                <?php else: ?>
                    <?php foreach ($eventos as $evento): ?>
                        <?php $accion = (string)$evento['accion']; ?>
                        <tr>
                            <td class="small text-muted text-nowrap"><?php echo e($evento['fecha']); ?></td>
                            <td><?php echo isset($iconos[$accion]) ? $iconos[$accion] : '·'; ?>
                                <b><?php echo e($evento['usuario']); ?></b></td>
                            <td><?php echo e($accion); ?></td>
                            <td class="small"><?php echo e($evento['detalle']); ?></td>
                            <td class="small text-muted"><?php echo e($evento['ip']); ?></td>
                        </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>
</div>

<?php terminar_pagina(); ?>
