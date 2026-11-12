<?php
/**
 * Historial completo con búsqueda, filtros y paginación.
 *
 * @var array  $registros
 * @var string $busqueda
 * @var string $desde
 * @var string $hasta
 * @var string $estado
 * @var int    $pagina
 * @var int    $total_paginas
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

$usuario = usuario_actual();
iniciar_pagina('Mis Actividades', 'listado', 'list');
?>

<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
    <h2 class="mb-0"><i class="fas fa-list"></i> <?php echo es_admin() ? 'Todas las Actividades' : 'Mis Actividades'; ?></h2>
    <a href="<?php echo e(url('inicio')); ?>" class="btn btn-primary">
        <i class="fas fa-plus-circle"></i> Nuevo Registro
    </a>
</div>

<div class="card">
    <div class="card-body">
        <form method="GET" action="<?php echo e(url('listado')); ?>" class="row g-2 align-items-end">
            <input type="hidden" name="ruta" value="listado">
            <div class="col-md-4">
                <label class="form-label small">Buscar</label>
                <input type="search" name="q" value="<?php echo e($busqueda); ?>" class="form-control"
                       placeholder="Texto, solicitante, descripción…">
            </div>
            <div class="col-md-2">
                <label class="form-label small">Desde</label>
                <input type="date" name="fecha_inicio" value="<?php echo e($desde); ?>" class="form-control">
            </div>
            <div class="col-md-2">
                <label class="form-label small">Hasta</label>
                <input type="date" name="fecha_fin" value="<?php echo e($hasta); ?>" class="form-control">
            </div>
            <div class="col-md-2">
                <label class="form-label small">Estado</label>
                <select name="estado" class="form-select">
                    <?php foreach (array('Todos', 'Sí', 'No') as $opcion): ?>
                        <option value="<?php echo e($opcion); ?>"<?php echo $estado === $opcion ? ' selected' : ''; ?>>
                            <?php echo e($opcion); ?>
                        </option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div class="col-md-2 d-flex gap-2">
                <button class="btn btn-primary flex-grow-1"><i class="fas fa-search"></i> Filtrar</button>
                <a href="<?php echo e(url('listado')); ?>" class="btn btn-outline-secondary" title="Limpiar">
                    <i class="fas fa-eraser"></i>
                </a>
            </div>
        </form>
    </div>
</div>

<p class="text-muted small">
    <?php echo count($registros); ?> registro(s) encontrado(s).
    <?php if ($busqueda !== ''): ?>Búsqueda: «<?php echo e($busqueda); ?>».<?php endif; ?>
</p>

<div class="table-responsive">
    <table class="table table-hover align-middle bg-white">
        <thead class="table-light">
            <tr>
                <th>Fecha</th>
                <th>Actividad</th>
                <th>Ubicación</th>
                <th>Solicitante</th>
                <th>Tipo</th>
                <th>Medio</th>
                <th>Estado</th>
                <th class="text-end">Acciones</th>
            </tr>
        </thead>
        <tbody>
        <?php if (empty($registros)): ?>
            <tr><td colspan="8" class="text-center text-muted py-5">
                No se encontraron actividades con los filtros seleccionados
            </td></tr>
        <?php else: ?>
            <?php $inicio = ($pagina - 1) * $por_pagina; ?>
            <?php foreach (array_slice($registros, $inicio, $por_pagina) as $fila): ?>
                <?php
                $texto = (string)$fila['tipo_actividad'];
                $visible = (largo($texto) > 60) ? recortar($texto, 57) . '...' : $texto;
                $color = ((string)$fila['cumplido'] === 'Sí') ? 'success' : 'secondary';
                ?>
                <tr>
                    <td class="text-nowrap"><?php echo e(fecha_corta($fila['fecha'])); ?></td>
                    <td title="<?php echo e($texto . "\n" . $fila['descripcion']); ?>"><?php echo e($visible); ?></td>
                    <td><?php echo e($fila['dependencia']); ?></td>
                    <td><?php echo e($fila['solicitante']); ?></td>
                    <td><?php echo e($fila['tipo_solicitud']); ?></td>
                    <td><?php echo e($fila['medio_solicitud']); ?></td>
                    <td><span class="badge bg-<?php echo $color; ?>"><?php echo e($fila['cumplido']); ?></span></td>
                    <td class="text-end text-nowrap">
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

<?php if ($total_paginas > 1): ?>
    <?php
    $parametros = array(
        'q' => $busqueda,
        'fecha_inicio' => $desde,
        'fecha_fin' => $hasta,
        'estado' => $estado,
    );
    ?>
    <nav>
        <ul class="pagination justify-content-center flex-wrap">
            <?php for ($i = 1; $i <= $total_paginas; $i++): ?>
                <?php $parametros['pagina'] = $i; ?>
                <li class="page-item<?php echo $i === $pagina ? ' active' : ''; ?>">
                    <a class="page-link" href="<?php echo e(url('listado', $parametros)); ?>"><?php echo $i; ?></a>
                </li>
            <?php endfor; ?>
        </ul>
    </nav>
<?php endif; ?>

<div class="mt-3 d-flex gap-2 flex-wrap">
    <a href="<?php echo e(url('exportar')); ?>" class="btn btn-outline-success btn-sm">
        <i class="fas fa-file-excel"></i> Exportar a Excel
    </a>
    <?php if (!empty($busqueda) || $desde !== '' || $hasta !== '' || $estado !== 'Todos'): ?>
        <a href="<?php echo e(url('listado')); ?>" class="btn btn-outline-secondary btn-sm">
            Quitar filtros
        </a>
    <?php endif; ?>
</div>

<?php terminar_pagina(); ?>
