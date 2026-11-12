<?php
/**
 * Panel de Mesa de Ayuda / Gestión de Tickets por Técnicos
 *
 * @var array  $tickets
 * @var string $filtroEstado
 * @var array  $usuarios
 * @var array  $actividades
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

$usuario = usuario_actual();
iniciar_pagina('Mesa de Ayuda - Tickets', 'tickets', 'headset');

$conteoPendientes = 0;
$conteoEnProceso = 0;
$conteoResueltos = 0;
foreach ($tickets as $t) {
    if ($t['estado'] === 'Pendiente') $conteoPendientes++;
    elseif ($t['estado'] === 'En proceso') $conteoEnProceso++;
    elseif ($t['estado'] === 'Resuelto') $conteoResueltos++;
}
?>

<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
    <div>
        <h2 class="mb-0"><i class="fas fa-headset text-primary me-2"></i> Mesa de Ayuda - Tickets</h2>
        <span class="text-muted small">Recepción de solicitudes y conversión automática a actividades oficiales</span>
    </div>
    <div>
        <a href="ticket.php" target="_blank" class="btn btn-outline-primary">
            <i class="fas fa-external-link-alt me-1"></i> Abrir Portal Público de Radicación
        </a>
    </div>
</div>

<!-- Tarjetas resumen de métricas -->
<div class="row g-3 mb-4">
    <div class="col-md-4">
        <div class="card border-0 shadow-sm bg-warning bg-opacity-25 border-start border-warning border-4">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="text-muted small fw-bold">PENDIENTES POR TOMAR</span>
                        <h3 class="mb-0 fw-bold text-dark"><?php echo $conteoPendientes; ?></h3>
                    </div>
                    <i class="fas fa-clock fa-2x text-warning"></i>
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card border-0 shadow-sm bg-info bg-opacity-25 border-start border-info border-4">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="text-muted small fw-bold">EN ATENCIÓN ACTUALMENTE</span>
                        <h3 class="mb-0 fw-bold text-dark"><?php echo $conteoEnProceso; ?></h3>
                    </div>
                    <i class="fas fa-tools fa-2x text-info"></i>
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card border-0 shadow-sm bg-success bg-opacity-25 border-start border-success border-4">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="text-muted small fw-bold">RESUELTOS Y CONVERTIDOS</span>
                        <h3 class="mb-0 fw-bold text-dark"><?php echo $conteoResueltos; ?></h3>
                    </div>
                    <i class="fas fa-check-double fa-2x text-success"></i>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Filtros de búsqueda -->
<div class="card shadow-sm mb-4">
    <div class="card-body py-3">
        <form method="GET" action="<?php echo e(url('tickets')); ?>" class="row g-2 align-items-center">
            <input type="hidden" name="ruta" value="tickets">
            <div class="col-auto">
                <label class="form-label mb-0 fw-bold small"><i class="fas fa-filter me-1"></i> Filtrar por estado:</label>
            </div>
            <div class="col-auto">
                <select name="estado" class="form-select form-select-sm" onchange="this.form.submit()">
                    <option value="Todos" <?php echo $filtroEstado === 'Todos' ? 'selected' : ''; ?>>Todos los tickets</option>
                    <option value="Pendiente" <?php echo $filtroEstado === 'Pendiente' ? 'selected' : ''; ?>>Solo Pendientes</option>
                    <option value="En proceso" <?php echo $filtroEstado === 'En proceso' ? 'selected' : ''; ?>>Solo En Proceso</option>
                    <option value="Resuelto" <?php echo $filtroEstado === 'Resuelto' ? 'selected' : ''; ?>>Solo Resueltos</option>
                </select>
            </div>
        </form>
    </div>
</div>

<!-- Tabla de tickets -->
<div class="card shadow-sm">
    <div class="card-body p-0">
        <div class="table-responsive">
            <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                    <tr>
                        <th style="width: 130px;">Radicado</th>
                        <th>Dependencia / Solicitante</th>
                        <th>Tipo / Prioridad</th>
                        <th>Descripción</th>
                        <th>Estado</th>
                        <th>Técnico</th>
                        <th class="text-end" style="width: 160px;">Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (empty($tickets)): ?>
                        <tr>
                            <td colspan="7" class="text-center py-5 text-muted">
                                <i class="fas fa-inbox fa-3x mb-3 text-secondary opacity-50"></i>
                                <p class="mb-0">No se encontraron tickets en esta categoría.</p>
                            </td>
                        </tr>
                    <?php else: ?>
                        <?php foreach ($tickets as $t): ?>
                            <?php
                                $badgeClass = 'bg-warning text-dark';
                                if ($t['estado'] === 'En proceso') $badgeClass = 'bg-info text-dark';
                                elseif ($t['estado'] === 'Resuelto') $badgeClass = 'bg-success text-white';

                                $prioClass = 'bg-secondary';
                                if ($t['prioridad'] === 'Alta') $prioClass = 'bg-danger text-white';
                                elseif ($t['prioridad'] === 'Urgente') $prioClass = 'bg-danger bg-opacity-75 text-white';
                                elseif ($t['prioridad'] === 'Media') $prioClass = 'bg-primary text-white';
                            ?>
                            <tr>
                                <td>
                                    <strong class="text-primary"><?php echo e($t['radicado']); ?></strong><br>
                                    <small class="text-muted"><?php echo e(substr($t['fecha_creacion'], 0, 16)); ?></small>
                                </td>
                                <td>
                                    <strong><?php echo e($t['dependencia']); ?></strong><br>
                                    <span class="text-muted small"><i class="fas fa-user me-1"></i><?php echo e($t['solicitante']); ?></span>
                                    <?php if (!empty($t['telefono'])): ?>
                                        <br><a href="https://wa.me/57<?php echo preg_replace('/\D/', '', $t['telefono']); ?>" target="_blank" class="text-success small text-decoration-none">
                                            <i class="fab fa-whatsapp me-1"></i><?php echo e($t['telefono']); ?>
                                        </a>
                                    <?php endif; ?>
                                </td>
                                <td>
                                    <span><?php echo e($t['tipo_solicitud']); ?></span><br>
                                    <span class="badge <?php echo $prioClass; ?>" style="font-size: 0.75rem;"><?php echo e($t['prioridad']); ?></span>
                                </td>
                                <td>
                                    <div style="max-width: 320px;" class="small text-truncate" title="<?php echo e($t['descripcion']); ?>">
                                        <?php echo e($t['descripcion']); ?>
                                    </div>
                                </td>
                                <td>
                                    <span class="badge <?php echo $badgeClass; ?>"><?php echo e($t['estado']); ?></span>
                                </td>
                                <td>
                                    <?php if (!empty($t['tecnico_asignado'])): ?>
                                        <span class="badge bg-light text-dark border">
                                            <i class="fas fa-user-cog me-1"></i><?php echo e($t['tecnico_asignado']); ?>
                                        </span>
                                    <?php else: ?>
                                        <span class="text-muted small fst-italic">Sin asignar</span>
                                    <?php endif; ?>
                                </td>
                                <td class="text-end">
                                    <?php if ($t['estado'] === 'Pendiente'): ?>
                                        <form method="POST" action="<?php echo e(url('ticket_tomar')); ?>" class="d-inline">
                                            <?php echo csrf_campo(); ?>
                                            <input type="hidden" name="id" value="<?php echo (int)$t['id']; ?>">
                                            <button type="submit" class="btn btn-sm btn-outline-primary" title="Asignarme este ticket y comenzar atención">
                                                <i class="fas fa-hand-holding me-1"></i> Tomar
                                            </button>
                                        </form>
                                    <?php elseif ($t['estado'] === 'En proceso'): ?>
                                        <button type="button" class="btn btn-sm btn-success" data-bs-toggle="modal" data-bs-target="#modalResolver<?php echo $t['id']; ?>" title="Finalizar ticket y registrar actividades oficiales">
                                            <i class="fas fa-check-circle me-1"></i> Resolver
                                        </button>
                                    <?php else: ?>
                                        <button type="button" class="btn btn-sm btn-outline-secondary" data-bs-toggle="modal" data-bs-target="#modalDetalle<?php echo $t['id']; ?>">
                                            <i class="fas fa-eye me-1"></i> Detalle
                                        </button>
                                    <?php endif; ?>
                                </td>
                            </tr>

                            <!-- MODAL RESOLVER TICKET Y ASIGNAR COLABORADORES -->
                            <?php if ($t['estado'] === 'En proceso'): ?>
                                <div class="modal fade" id="modalResolver<?php echo $t['id']; ?>" tabindex="-1">
                                    <div class="modal-dialog modal-lg">
                                        <div class="modal-content">
                                            <form method="POST" action="<?php echo e(url('ticket_resolver')); ?>">
                                                <?php echo csrf_campo(); ?>
                                                <input type="hidden" name="id" value="<?php echo (int)$t['id']; ?>">
                                                <div class="modal-header bg-success text-white">
                                                    <h5 class="modal-title"><i class="fas fa-check-circle me-2"></i> Resolver Ticket <?php echo e($t['radicado']); ?></h5>
                                                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                                                </div>
                                                <div class="modal-body">
                                                    <!-- Ficha informativa de lo que se solicitó -->
                                                    <div class="p-3 mb-3 bg-light rounded border border-start border-primary border-3">
                                                        <div class="row g-2 small">
                                                            <div class="col-md-6">
                                                                <span class="text-muted d-block">Ubicación / Dependencia:</span>
                                                                <strong class="text-dark"><i class="fas fa-building text-primary me-1"></i> <?php echo e($t['dependencia']); ?></strong>
                                                            </div>
                                                            <div class="col-md-6">
                                                                <span class="text-muted d-block">Solicitante:</span>
                                                                <strong class="text-dark"><i class="fas fa-user text-primary me-1"></i> <?php echo e($t['solicitante']); ?></strong>
                                                            </div>
                                                            <div class="col-12 mt-2 pt-2 border-top">
                                                                <span class="text-muted d-block">Requerimiento Solicitado:</span>
                                                                <div class="text-dark fst-italic">"<?php echo nl2br(e($t['descripcion'])); ?>"</div>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div class="row g-3 mb-3">
                                                        <div class="col-md-6">
                                                            <label class="form-label fw-bold">Fecha de Atención / Actividad *</label>
                                                            <div class="input-group">
                                                                <span class="input-group-text bg-white"><i class="fas fa-calendar-alt text-primary"></i></span>
                                                                <input type="date" name="fecha_actividad" class="form-control" value="<?php echo date('Y-m-d'); ?>" required>
                                                            </div>
                                                            <small class="text-muted">Fecha que quedará en el informe oficial.</small>
                                                        </div>
                                                        <div class="col-md-6">
                                                            <label class="form-label fw-bold">Tipo de Actividad Oficial (Informe)</label>
                                                            <select name="tipo_actividad" class="form-select">
                                                                <?php foreach ($actividades as $act): ?>
                                                                    <option value="<?php echo e($act); ?>"><?php echo e($act); ?></option>
                                                                <?php endforeach; ?>
                                                            </select>
                                                        </div>
                                                    </div>

                                                    <div class="mb-3">
                                                        <label class="form-label fw-bold">Detalle de la Solución Brindada *</label>
                                                        <textarea name="solucion" class="form-control" rows="3" placeholder="Describa qué se realizó (ej: Se configuró la impresora en red, se instalaron controladores y se realizó prueba de impresión exitosa)..." required></textarea>
                                                    </div>



                                                    <div class="mb-3">
                                                        <label class="form-label fw-bold d-block"><i class="fas fa-users text-primary me-1"></i> ¿Participaron otros técnicos en esta actividad?</label>
                                                        <div class="p-3 bg-light rounded border">
                                                            <small class="text-muted d-block mb-2">Marque los técnicos que colaboraron para que a ellos también se les registre automáticamente la actividad en su informe mensual:</small>
                                                            <div class="row g-2">
                                                                <?php foreach ($usuarios as $u): ?>
                                                                    <?php if ($u !== $usuario): ?>
                                                                        <div class="col-sm-6 col-md-4">
                                                                            <div class="form-check">
                                                                                <input class="form-check-input" type="checkbox" name="colaboradores[]" value="<?php echo e($u); ?>" id="colab_<?php echo $t['id'] . '_' . e($u); ?>">
                                                                                <label class="form-check-label" for="colab_<?php echo $t['id'] . '_' . e($u); ?>">
                                                                                    <?php echo e($u); ?>
                                                                                </label>
                                                                            </div>
                                                                        </div>
                                                                    <?php endif; ?>
                                                                <?php endforeach; ?>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div class="modal-footer">
                                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                                                    <button type="submit" class="btn btn-success">
                                                        <i class="fas fa-save me-1"></i> Guardar y Generar Actividades
                                                    </button>
                                                </div>
                                            </form>
                                        </div>
                                    </div>
                                </div>
                            <?php endif; ?>

                            <!-- MODAL DETALLE DE TICKET RESUELTO -->
                            <?php if ($t['estado'] === 'Resuelto'): ?>
                                <div class="modal fade" id="modalDetalle<?php echo $t['id']; ?>" tabindex="-1">
                                    <div class="modal-dialog">
                                        <div class="modal-content">
                                            <div class="modal-header">
                                                <h5 class="modal-title">Detalle del Ticket <?php echo e($t['radicado']); ?></h5>
                                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                            </div>
                                            <div class="modal-body">
                                                <p><strong>Dependencia:</strong> <?php echo e($t['dependencia']); ?></p>
                                                <p><strong>Solicitante:</strong> <?php echo e($t['solicitante']); ?></p>
                                                <p><strong>Fecha Solicitud:</strong> <?php echo e($t['fecha_creacion']); ?></p>
                                                <p><strong>Fecha Solución:</strong> <?php echo e($t['fecha_cierre']); ?></p>
                                                <p><strong>Técnico Principal:</strong> <?php echo e($t['tecnico_asignado']); ?></p>
                                                <?php
                                                    $colabs = json_decode((string)$t['tecnicos_colaboradores'], true);
                                                    if (!empty($colabs) && is_array($colabs)):
                                                ?>
                                                    <p><strong>Colaboradores:</strong> <?php echo e(implode(', ', $colabs)); ?></p>
                                                <?php endif; ?>
                                                <hr>
                                                <h6>Solución Registrada:</h6>
                                                <div class="p-3 bg-light rounded border">
                                                    <?php echo nl2br(e($t['solucion'])); ?>
                                                </div>
                                            </div>
                                            <div class="modal-footer">
                                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cerrar</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            <?php endif; ?>

                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>
</div>

<?php terminar_pagina(); ?>
