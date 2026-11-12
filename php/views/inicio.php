<?php
/**
 * Página principal: registro rápido, buscador y últimos movimientos.
 *
 * @var array $registros    registros visibles para el usuario
 * @var array $pendientes   actividades asignadas sin registrar
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

$usuario = usuario_actual();
$admin = es_admin();
iniciar_pagina('Inicio', 'inicio', 'tasks');
?>

<?php if (!$admin): ?>
    <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
        <h2 class="mb-0"><i class="fas fa-plus-circle text-primary me-2"></i> Nuevo Registro</h2>
        <a href="<?php echo e(url('tickets')); ?>" class="btn btn-outline-primary shadow-sm">
            <i class="fas fa-headset me-1"></i> Mesa de Ayuda / Tickets
            <?php
                $pend = function_exists('ticket_conteo_pendientes') ? ticket_conteo_pendientes() : 0;
                if ($pend > 0) echo ' <span class="badge bg-danger ms-1">' . $pend . '</span>';
            ?>
        </a>
    </div>

    <form action="<?php echo e(url('agregar_registro')); ?>" method="POST"
          onsubmit="this.querySelector('button[type=submit]').disabled = true;">
        <?php echo csrf_campo(); ?>
        <div class="row">
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">📝 Actividad:</label>
                    <select name="actividad" class="form-select" required>
                        <option value="">Seleccionar actividad...</option>
                        <?php echo opciones_select($actividades, '', true); ?>
                    </select>
                    <?php if (empty($actividades)): ?>
                        <div class="form-text text-danger">
                            No tiene actividades propias todavía. Agréguelas en «Mi Gestión».
                        </div>
                    <?php endif; ?>
                </div>
                <div class="mb-3">
                    <label class="form-label">📍 Ubicación:</label>
                    <select name="ubicacion" class="form-select" required>
                        <option value="">Seleccionar ubicación...</option>
                        <?php echo opciones_select($ubicaciones); ?>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label">🔧 Tipo de Solicitud:</label>
                    <select name="tipo_solicitud" class="form-select" required>
                        <option value="">Seleccionar tipo...</option>
                        <?php echo opciones_select($tipos_solicitud); ?>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label">👤 Solicitante:</label>
                    <input type="text" name="solicitante" class="form-control"
                           placeholder="Nombre de quien solicita" maxlength="120" required>
                </div>
            </div>
            <div class="col-md-6">
                <div class="mb-4">
                    <label class="form-label">📞 Medio de Solicitud:</label>
                    <select name="medio_solicitud" class="form-select" required>
                        <option value="">Seleccionar medio...</option>
                        <?php echo opciones_select($medios_solicitud); ?>
                    </select>
                </div>
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label class="form-label">✅ Cumplido:</label>
                            <select name="cumplido" class="form-select">
                                <option value="Sí">Sí</option>
                                <option value="No">No</option>
                            </select>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label class="form-label">📅 Fecha Atención:</label>
                            <input type="date" name="fecha_atencion" class="form-control" value="<?php echo e(hoy()); ?>">
                        </div>
                    </div>
                </div>
                <div class="mb-3">
                    <label class="form-label">📋 Observaciones:</label>
                    <textarea name="observaciones" class="form-control" rows="3"
                              maxlength="1000" placeholder="Detalles adicionales..."></textarea>
                </div>
            </div>
        </div>
        <button type="submit" class="btn btn-primary btn-lg">
            <i class="fas fa-save"></i> Guardar Registro
        </button>
    </form>
<?php endif; ?>

<?php if ($admin): ?>
    <div class="card border-warning mb-4">
        <div class="card-header bg-warning text-dark">
            <h5 class="mb-0"><i class="fas fa-file-import"></i> Importar registros desde Excel</h5>
        </div>
        <div class="card-body">
            <form method="POST" action="<?php echo e(url('importar_excel')); ?>" enctype="multipart/form-data">
                <?php echo csrf_campo(); ?>
                <div class="row g-3 align-items-end">
                    <div class="col-md-8">
                        <label class="form-label">Archivo .xlsx</label>
                        <input type="file" name="archivo" class="form-control" accept=".xlsx" required>
                        <div class="form-text">Solo se agregan registros que no existan. No se elimina nada.</div>
                    </div>
                    <div class="col-md-4">
                        <button class="btn btn-warning w-100"><i class="fas fa-upload"></i> Importar</button>
                    </div>
                </div>
            </form>
            <hr>
            <details>
                <summary class="text-danger small">Reemplazar toda la tabla con un Excel (operación delicada)</summary>
                <form method="POST" action="<?php echo e(url('reemplazar_registros')); ?>" enctype="multipart/form-data"
                      class="row g-2 mt-2" onsubmit="return confirm('¿Reemplazar TODOS los registros con el archivo? Se guardará un respaldo antes.')">
                    <?php echo csrf_campo(); ?>
                    <div class="col-md-5">
                        <input type="file" name="archivo" class="form-control" accept=".xlsx" required>
                    </div>
                    <div class="col-md-4">
                        <input type="text" name="confirmacion" class="form-control"
                               placeholder="Escriba REEMPLAZAR_DATOS" required>
                    </div>
                    <div class="col-md-3">
                        <button class="btn btn-outline-danger w-100">Reemplazar</button>
                    </div>
                </form>
            </details>
        </div>
    </div>
<?php endif; ?>

<div class="card border-0 shadow-sm mb-4">
    <div class="card-body p-4">
        <h5 class="mb-1"><i class="fas fa-search text-primary me-2"></i>Buscar en mis actividades</h5>
        <p class="text-muted small mb-3">
            Busca en todo el historial: descripción, observaciones, solicitante, ubicación, tipo…
            No importan las tildes ni las mayúsculas.
        </p>
        <form action="<?php echo e(url('listado')); ?>" method="GET" class="row g-2">
            <input type="hidden" name="ruta" value="listado">
            <div class="col-12 col-md">
                <input type="search" name="q" class="form-control form-control-lg"
                       placeholder="Ej.: revisión de equipo, Juan Pérez, oficina…" aria-label="Buscar actividades">
            </div>
            <div class="col-12 col-md-auto d-flex gap-2">
                <button type="submit" class="btn btn-primary btn-lg flex-grow-1">
                    <i class="fas fa-search me-1"></i> Buscar
                </button>
                <a href="<?php echo e(url('listado')); ?>" class="btn btn-outline-secondary btn-lg">Ver historial</a>
            </div>
        </form>
    </div>
</div>

<?php if (!$admin && !empty($pendientes)): ?>
    <div class="card border-info mb-4">
        <div class="card-header bg-info text-white">
            <h5 class="mb-0"><i class="fas fa-tasks"></i> Actividades pendientes de registrar (<?php echo count($pendientes); ?>)</h5>
        </div>
        <div class="card-body">
            <p class="small text-muted mb-2">
                Estas actividades están asignadas a usted y todavía no tienen registro. Puede registrarlas
                una por una o descargar el Excel, llenarlo y subirlo completo.
            </p>
            <ul class="mb-3">
                <?php foreach (array_slice($pendientes, 0, 8) as $pendiente): ?>
                    <li><?php echo e($pendiente['actividad']); ?></li>
                <?php endforeach; ?>
                <?php if (count($pendientes) > 8): ?>
                    <li class="text-muted">y <?php echo count($pendientes) - 8; ?> más…</li>
                <?php endif; ?>
            </ul>
            <a href="<?php echo e(url('descargar_pendientes')); ?>" class="btn btn-outline-info btn-sm">
                <i class="fas fa-download me-1"></i> Descargar Excel con mis pendientes
            </a>
        </div>
    </div>
<?php endif; ?>

<hr class="my-4">

<div class="d-flex justify-content-between align-items-center mb-3">
    <h3 class="mb-0"><i class="fas fa-history"></i> Registros Recientes</h3>
    <a href="<?php echo e(url('inicio')); ?>" class="btn btn-outline-secondary btn-sm">
        <i class="fas fa-sync-alt"></i> Actualizar
    </a>
</div>
<div class="table-responsive">
    <table class="table table-hover align-middle">
        <thead class="table-light">
            <tr>
                <th>Fecha</th>
                <th>Actividad</th>
                <th>Ubicación</th>
                <th>Tipo</th>
                <th>Cumplido</th>
                <th class="text-end">Acciones</th>
            </tr>
        </thead>
        <tbody>
        <?php if (empty($registros)): ?>
            <tr><td colspan="6" class="text-center text-muted py-4">No hay registros recientes</td></tr>
        <?php else: ?>
            <?php foreach (array_slice($registros, 0, 10) as $fila): ?>
                <?php
                $texto = (string)$fila['tipo_actividad'];
                $visible = (largo($texto) > 40) ? recortar($texto, 37) . '...' : $texto;
                ?>
                <tr>
                    <td><?php echo e(fecha_corta($fila['fecha'])); ?></td>
                    <td title="<?php echo e($texto); ?>"><?php echo e($visible); ?></td>
                    <td><?php echo e($fila['dependencia']); ?></td>
                    <td><?php echo e($fila['tipo_solicitud']); ?></td>
                    <td><?php echo e($fila['cumplido']); ?></td>
                    <td class="text-end">
                        <a href="<?php echo e(url('editar_registro', array('id_registro' => $fila['id']))); ?>"
                           class="btn btn-sm btn-outline-primary border-0" title="Editar">
                            <i class="fas fa-edit"></i>
                        </a>
                        <form action="<?php echo e(url('eliminar_registro')); ?>" method="POST"
                              style="display:inline;" onsubmit="return confirm('¿Eliminar este registro?')">
                            <?php echo csrf_campo(); ?>
                            <input type="hidden" name="id_registro" value="<?php echo (int)$fila['id']; ?>">
                            <button type="submit" class="btn btn-sm btn-outline-danger border-0" title="Eliminar">
                                <i class="fas fa-trash-alt"></i>
                            </button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
        <?php endif; ?>
        </tbody>
    </table>
</div>

<?php terminar_pagina(); ?>
