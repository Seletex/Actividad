<?php
/**
 * Formulario de edición de un registro.
 *
 * @var array $registro
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

$usuario = usuario_actual();
iniciar_pagina('Editar registro', 'listado', 'edit');
?>

<div class="d-flex justify-content-between align-items-center mb-3">
    <h2 class="mb-0"><i class="fas fa-edit"></i> Editar Registro #<?php echo (int)$registro['id']; ?></h2>
    <a href="<?php echo e(url('listado')); ?>" class="btn btn-outline-secondary btn-sm">
        <i class="fas fa-arrow-left"></i> Volver
    </a>
</div>

<form action="<?php echo e(url('actualizar_registro')); ?>" method="POST"
      onsubmit="this.querySelector('button[type=submit]').disabled = true;">
    <?php echo csrf_campo(); ?>
    <input type="hidden" name="id_registro" value="<?php echo (int)$registro['id']; ?>">

    <div class="row">
        <div class="col-md-6">
            <div class="mb-3">
                <label class="form-label">📝 Actividad:</label>
                <select name="actividad" class="form-select" required>
                    <?php echo opciones_select($actividades, $registro['tipo_actividad'], true); ?>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">📍 Ubicación:</label>
                <select name="ubicacion" class="form-select" required>
                    <?php echo opciones_select($ubicaciones, $registro['dependencia']); ?>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">🔧 Tipo de Solicitud:</label>
                <select name="tipo_solicitud" class="form-select" required>
                    <?php echo opciones_select($tipos_solicitud, $registro['tipo_solicitud']); ?>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">👤 Solicitante:</label>
                <input type="text" name="solicitante" class="form-control" maxlength="120"
                       value="<?php echo e($registro['solicitante']); ?>" required>
            </div>
            <?php if (es_admin()): ?>
                <div class="mb-3">
                    <label class="form-label">👥 Usuario dueño del registro:</label>
                    <input type="text" class="form-control" value="<?php echo e($registro['usuario']); ?>" disabled>
                </div>
            <?php endif; ?>
        </div>
        <div class="col-md-6">
            <div class="mb-4">
                <label class="form-label">📞 Medio de Solicitud:</label>
                <select name="medio_solicitud" class="form-select" required>
                    <?php echo opciones_select($medios_solicitud, $registro['medio_solicitud']); ?>
                </select>
            </div>
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">✅ Cumplido:</label>
                        <select name="cumplido" class="form-select">
                            <option value="Sí"<?php echo $registro['cumplido'] === 'Sí' ? ' selected' : ''; ?>>Sí</option>
                            <option value="No"<?php echo $registro['cumplido'] === 'No' ? ' selected' : ''; ?>>No</option>
                        </select>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">📅 Fecha Atención:</label>
                        <input type="date" name="fecha_atencion" class="form-control"
                               value="<?php echo e(fecha_corta($registro['fecha_atencion'])); ?>">
                    </div>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">🗓️ Fecha del registro:</label>
                <input type="text" class="form-control" value="<?php echo e($registro['fecha']); ?>" disabled>
                <div class="form-text">Si cambia la fecha de atención, también se actualiza esta fecha.</div>
            </div>
            <div class="mb-3">
                <label class="form-label">📋 Observaciones:</label>
                <textarea name="observaciones" class="form-control" rows="4" maxlength="1000"><?php echo e($registro['observaciones']); ?></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">📄 Descripción:</label>
                <textarea name="descripcion" class="form-control" rows="3" maxlength="2000"><?php echo e($registro['descripcion']); ?></textarea>
            </div>
        </div>
    </div>

    <button type="submit" class="btn btn-primary btn-lg"><i class="fas fa-save"></i> Guardar cambios</button>
    <a href="<?php echo e(url('listado')); ?>" class="btn btn-outline-secondary btn-lg">Cancelar</a>
</form>

<?php terminar_pagina(); ?>
