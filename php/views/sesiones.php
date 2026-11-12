<?php
/**
 * Sesiones activas (solo administrador).
 *
 * @var array  $sesiones
 * @var string $token_actual
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

iniciar_pagina('Sesiones activas', 'sesiones', 'user-clock');
?>

<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
    <h2 class="mb-0"><i class="fas fa-user-clock"></i> Sesiones activas</h2>
    <div class="d-flex gap-2">
        <a href="<?php echo e(url('gestion')); ?>" class="btn btn-outline-secondary btn-sm">
            <i class="fas fa-arrow-left"></i> Volver
        </a>
        <form action="<?php echo e(url('revocar_todas_sesiones')); ?>" method="POST"
              onsubmit="return confirm('¿Cerrar TODAS las sesiones de todos los usuarios? Todos deberán volver a entrar.')">
            <?php echo csrf_campo(); ?>
            <button class="btn btn-outline-danger btn-sm"><i class="fas fa-door-open"></i> Cerrar todas</button>
        </form>
    </div>
</div>

<p class="text-muted small">
    Cerrar una sesión termina el acceso de esa persona de inmediato, sin esperar a que expire la cookie.
</p>

<div class="card">
    <div class="card-body p-0">
        <div class="table-responsive">
            <table class="table table-sm align-middle mb-0">
                <thead class="table-light">
                    <tr><th>Usuario</th><th>IP</th><th>Inicio</th><th>Última actividad</th><th></th></tr>
                </thead>
                <tbody>
                <?php if (empty($sesiones)): ?>
                    <tr><td colspan="5" class="text-center text-muted py-4">No hay sesiones activas</td></tr>
                <?php else: ?>
                    <?php foreach ($sesiones as $sesion): ?>
                        <?php $propia = ((string)$sesion['token'] === (string)$token_actual); ?>
                        <tr>
                            <td>
                                <?php echo e($sesion['usuario']); ?>
                                <?php if ($propia): ?>
                                    <span class="badge bg-info text-dark">esta sesión</span>
                                <?php endif; ?>
                            </td>
                            <td><?php echo e($sesion['ip']); ?></td>
                            <td><?php echo e($sesion['creado']); ?></td>
                            <td><?php echo e($sesion['visto']); ?></td>
                            <td class="text-end">
                                <form action="<?php echo e(url('revocar_sesion')); ?>" method="POST" style="display:inline;">
                                    <?php echo csrf_campo(); ?>
                                    <input type="hidden" name="token" value="<?php echo e($sesion['token']); ?>">
                                    <button type="submit" class="btn btn-sm btn-outline-danger border-0">Cerrar</button>
                                </form>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>
</div>

<?php terminar_pagina(); ?>
