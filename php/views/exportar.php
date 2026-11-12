<?php
/**
 * Exportación a Excel/CSV y datos del contrato para el informe.
 *
 * @var array  $contrato
 * @var array  $actividades
 * @var array  $usuarios
 * @var array  $stats
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

$usuario = usuario_actual();
iniciar_pagina('Exportar', 'exportar', 'file-export');

$valor_contrato = function ($clave) use ($contrato) {
    return isset($contrato[$clave]) ? (string)$contrato[$clave] : '';
};
?>

<h2 class="mb-3"><i class="fas fa-file-export"></i> Exportar Actividades</h2>

<div class="row">
    <div class="col-lg-8">
        <div class="card">
            <div class="card-header"><h5><i class="fas fa-filter text-primary me-2"></i> Filtros del informe</h5></div>
            <div class="card-body">
                <form method="POST" action="<?php echo e(url('exportar')); ?>" onsubmit="this.querySelector('button[type=submit]').disabled = true;">
                    <?php echo csrf_campo(); ?>
                    <div class="row g-3">
                        <div class="col-md-4">
                            <label class="form-label">Desde</label>
                            <input type="date" name="fecha_inicio" class="form-control">
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">Hasta</label>
                            <input type="date" name="fecha_fin" class="form-control">
                        </div>
                        <?php if (es_admin()): ?>
                            <div class="col-md-4">
                                <label class="form-label">Usuario</label>
                                <select class="form-select" name="usuario_filtro">
                                    <option value="Todos" selected>Todos los usuarios</option>
                                    <?php echo opciones_select($usuarios); ?>
                                </select>
                            </div>
                        <?php endif; ?>
                        <div class="col-md-6">
                            <label class="form-label">Actividad (opcional)</label>
                            <select class="form-select" name="actividad">
                                <option value="">Todas</option>
                                <?php echo opciones_select($actividades, '', true); ?>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Formato</label>
                            <select class="form-select" name="formato">
                                <option value="excel">Excel (.xlsx)</option>
                                <option value="csv">CSV (.csv)</option>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Tipo de informe</label>
                            <select class="form-select" name="tipo_reporte">
                                <option value="detallado">Detallado</option>
                                <option value="final">Informe final</option>
                            </select>
                        </div>
                    </div>

                    <hr>

                    <h6 class="text-uppercase text-muted fw-bold small mb-3">Datos del contrato (salen en el informe)</h6>
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label small">Número de contrato</label>
                            <input type="text" name="contrato_nro" value="<?php echo e($valor_contrato('nro')); ?>" class="form-control">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label small">Nombre del contratista</label>
                            <input type="text" name="contrato_nombre" value="<?php echo e($valor_contrato('nombre')); ?>" class="form-control">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label small">Cédula</label>
                            <input type="text" name="contrato_cedula" value="<?php echo e($valor_contrato('cedula')); ?>" class="form-control">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label small">Supervisor</label>
                            <input type="text" name="contrato_supervisor" value="<?php echo e($valor_contrato('supervisor')); ?>" class="form-control">
                        </div>
                        <div class="col-12">
                            <label class="form-label small">Objeto del contrato</label>
                            <input type="text" name="contrato_objeto" value="<?php echo e($valor_contrato('objeto')); ?>" class="form-control">
                        </div>
                    </div>

                    <div class="mt-4 d-flex gap-2 flex-wrap">
                        <button type="submit" class="btn btn-success btn-lg">
                            <i class="fas fa-download"></i> Generar y descargar
                        </button>
                        <a href="<?php echo e(url('listado')); ?>" class="btn btn-outline-secondary btn-lg">Ver historial</a>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <div class="col-lg-4">
        <div class="card">
            <div class="card-header"><h5>Resumen de sus datos</h5></div>
            <div class="card-body">
                <p class="mb-1"><span class="text-muted small">Registros:</span> <b><?php echo (int)$stats['total_registros']; ?></b></p>
                <p class="mb-1"><span class="text-muted small">Tipos de actividad:</span> <b><?php echo (int)$stats['total_tipos_actividad']; ?></b></p>
                <p class="mb-1"><span class="text-muted small">Primer registro:</span> <b><?php echo e($stats['fecha_min'] !== '' ? $stats['fecha_min'] : 'N/A'); ?></b></p>
                <p class="mb-0"><span class="text-muted small">Último registro:</span> <b><?php echo e($stats['fecha_max'] !== '' ? $stats['fecha_max'] : 'N/A'); ?></b></p>
            </div>
        </div>

        <div class="card">
            <div class="card-header"><h5>Actividades pendientes</h5></div>
            <div class="card-body">
                <p class="text-muted small">
                    Descargue el Excel de actividades asignadas que aún no tienen registro.
                </p>
                <?php if (!es_admin()): ?>
                    <a href="<?php echo e(url('descargar_pendientes')); ?>" class="btn btn-outline-info btn-sm">
                        <i class="fas fa-download me-1"></i> Descargar plantilla
                    </a>
                <?php else: ?>
                    <span class="text-muted small">Disponible para usuarios que registran actividades.</span>
                <?php endif; ?>
            </div>
        </div>
    </div>
</div>

<?php terminar_pagina(); ?>
