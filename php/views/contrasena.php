<?php
/**
 * Cambio o configuración de contraseña.
 *
 * @var bool   $tiene_contrasena
 * @var bool   $forzado
 * @var string $error
 * @var string $mensaje
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

$usuario = usuario_actual();
$titulo = $tiene_contrasena ? 'Cambiar Contraseña' : 'Configurar Contraseña';
iniciar_pagina($titulo, 'gestion', 'key');
?>

<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5><i class="fas fa-key text-primary me-2"></i> <?php echo e($titulo); ?></h5>
            </div>
            <div class="card-body">
                <?php if ($forzado): ?>
                    <div class="alert alert-warning">
                        ⚠️ Por seguridad, debe cambiar su contraseña antes de continuar utilizando la plataforma.
                    </div>
                <?php endif; ?>
                <?php if ($error !== ''): ?>
                    <div class="alert alert-danger">❌ <?php echo e($error); ?></div>
                <?php endif; ?>
                <?php if ($mensaje !== ''): ?>
                    <div class="alert alert-success">✅ <?php echo e($mensaje); ?></div>
                <?php endif; ?>

                <form action="<?php echo e(url('cambiar_contrasena')); ?>" method="POST">
                    <?php echo csrf_campo(); ?>
                    <?php if ($tiene_contrasena && !$forzado): ?>
                        <div class="mb-3">
                            <label class="form-label">Contraseña actual</label>
                            <input type="password" name="contrasena_actual" class="form-control"
                                   autocomplete="current-password" required>
                        </div>
                    <?php endif; ?>
                    <div class="mb-3">
                        <label class="form-label">Nueva contraseña</label>
                        <input type="password" name="nueva_contrasena" class="form-control"
                               autocomplete="new-password" minlength="6" required>
                        <div class="form-text">Mínimo 6 caracteres.</div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Confirmar nueva contraseña</label>
                        <input type="password" name="confirmar_contrasena" class="form-control"
                               autocomplete="new-password" minlength="6" required>
                    </div>
                    <div class="d-grid">
                        <button type="submit" class="btn btn-primary"><?php echo e($titulo); ?></button>
                    </div>
                </form>

                <div class="text-center mt-3">
                    <?php if ($forzado): ?>
                        <a href="<?php echo e(url('logout')); ?>" class="btn btn-outline-secondary btn-sm">Salir</a>
                    <?php else: ?>
                        <a href="<?php echo e(url('gestion')); ?>" class="btn btn-outline-secondary btn-sm">Volver a Mi Gestión</a>
                    <?php endif; ?>
                </div>
            </div>
        </div>
    </div>
</div>

<?php terminar_pagina(); ?>
