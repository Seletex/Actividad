<?php
/**
 * Estadísticas con gráficos y tablas.
 *
 * @var array  $stats
 * @var string $desde
 * @var string $hasta
 * @var string $promedio
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

iniciar_pagina('Estadísticas', 'estadisticas', 'chart-line');
?>

<h2 class="mb-3"><i class="fas fa-chart-line"></i> Estadísticas</h2>

<form method="GET" action="<?php echo e(url('estadisticas')); ?>" class="row g-2 align-items-end mb-4">
    <input type="hidden" name="ruta" value="estadisticas">
    <div class="col-md-3">
        <label class="form-label small">Desde</label>
        <input type="date" name="fecha_inicio" value="<?php echo e($desde); ?>" class="form-control">
    </div>
    <div class="col-md-3">
        <label class="form-label small">Hasta</label>
        <input type="date" name="fecha_fin" value="<?php echo e($hasta); ?>" class="form-control">
    </div>
    <div class="col-md-3">
        <button class="btn btn-primary"><i class="fas fa-filter"></i> Aplicar</button>
        <a href="<?php echo e(url('estadisticas')); ?>" class="btn btn-outline-secondary">Todo</a>
    </div>
</form>

<div class="row">
    <?php
    $tarjetas = array(
        array('Total Registros', $stats['total_registros'], 'fa-clipboard-check', 'primary'),
        array('Tipos de Actividad', $stats['total_tipos_actividad'], 'fa-tags', 'success'),
        array('Promedio Diario', $promedio, 'fa-calendar-day', 'info'),
        array('Primer Registro', $desde !== '' ? $desde : ($stats['fecha_min'] !== '' ? $stats['fecha_min'] : 'N/A'), 'fa-calendar-alt', 'warning'),
    );
    foreach ($tarjetas as $tarjeta): ?>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <i class="fas <?php echo $tarjeta[2]; ?> fa-2x text-<?php echo $tarjeta[3]; ?> mb-2"></i>
                    <h3 class="mb-0"><?php echo e($tarjeta[1]); ?></h3>
                    <p class="text-muted small mb-0"><?php echo e($tarjeta[0]); ?></p>
                </div>
            </div>
        </div>
    <?php endforeach; ?>
</div>

<div class="row">
    <div class="col-lg-8">
        <div class="card">
            <div class="card-header"><h5>Actividades por mes</h5></div>
            <div class="card-body"><canvas id="graficoLinea" height="110"></canvas></div>
        </div>
    </div>
    <div class="col-lg-4">
        <div class="card">
            <div class="card-header"><h5>Cumplimiento</h5></div>
            <div class="card-body"><canvas id="graficoCumplimiento" height="200"></canvas></div>
        </div>
    </div>
</div>

<div class="card">
    <div class="card-header"><h5>Actividades más frecuentes</h5></div>
    <div class="card-body"><canvas id="graficoActividades" height="110"></canvas></div>
</div>

<div class="row">
    <div class="col-lg-6">
        <div class="card">
            <div class="card-header"><h5>Por usuario</h5></div>
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-sm align-middle mb-0">
                        <thead class="table-light">
                            <tr><th>Usuario</th><th class="text-center">Total</th><th class="text-center">% Cumplido</th><th>Última</th></tr>
                        </thead>
                        <tbody>
                        <?php if (empty($stats['usuarios'])): ?>
                            <tr><td colspan="4" class="text-center text-muted py-3">No hay datos disponibles</td></tr>
                        <?php else: ?>
                            <?php foreach ($stats['usuarios'] as $fila): ?>
                                <tr>
                                    <td class="fw-bold"><?php echo e($fila['usuario']); ?></td>
                                    <td class="text-center"><span class="badge bg-light text-dark"><?php echo (int)$fila['total']; ?></span></td>
                                    <td class="text-center"><?php echo e($fila['cumplimiento']); ?></td>
                                    <td class="small text-muted"><?php echo e($fila['ultima']); ?></td>
                                </tr>
                            <?php endforeach; ?>
                        <?php endif; ?>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    <div class="col-lg-6">
        <div class="card">
            <div class="card-header"><h5>Detalle por actividad</h5></div>
            <div class="card-body p-0">
                <div class="table-responsive" style="max-height:420px;overflow:auto;">
                    <table class="table table-sm align-middle mb-0">
                        <thead class="table-light">
                            <tr><th>Actividad</th><th class="text-center">Total</th><th class="text-center">Sí</th><th class="text-center">No</th><th class="text-center">%</th></tr>
                        </thead>
                        <tbody>
                        <?php if (empty($stats['actividades_stats'])): ?>
                            <tr><td colspan="5" class="text-center text-muted py-3">No hay datos disponibles</td></tr>
                        <?php else: ?>
                            <?php foreach ($stats['actividades_stats'] as $fila): ?>
                                <tr>
                                    <td class="small" title="<?php echo e($fila['actividad']); ?>">
                                        <?php echo e(recortar($fila['actividad'], 70)); ?>
                                    </td>
                                    <td class="text-center"><span class="badge bg-light text-dark"><?php echo (int)$fila['total']; ?></span></td>
                                    <td class="text-center"><span class="badge bg-success"><?php echo (int)$fila['cumplidos']; ?></span></td>
                                    <td class="text-center"><span class="badge bg-secondary"><?php echo (int)$fila['pendientes']; ?></span></td>
                                    <td class="text-center"><?php echo e($fila['porcentaje']); ?></td>
                                </tr>
                            <?php endforeach; ?>
                        <?php endif; ?>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
<script>
    const datosActividades = <?php echo json_html($stats['chart_actividades']); ?>;
    const datosCumplimiento = <?php echo json_html($stats['chart_cumplimiento']); ?>;
    const datosLinea = <?php echo json_html($stats['chart_linea']); ?>;

    new Chart(document.getElementById("graficoActividades"), {
        type: "bar",
        data: {
            labels: datosActividades.labels,
            datasets: [{ label: "Registros", data: datosActividades.data, backgroundColor: "#667eea" }]
        },
        options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } }
    });

    new Chart(document.getElementById("graficoCumplimiento"), {
        type: "doughnut",
        data: {
            labels: datosCumplimiento.labels,
            datasets: [{ data: datosCumplimiento.data, backgroundColor: ["#10b981", "#94a3b8"] }]
        },
        options: { plugins: { legend: { position: "bottom" } } }
    });

    new Chart(document.getElementById("graficoLinea"), {
        type: "line",
        data: {
            labels: datosLinea.labels,
            datasets: [{
                label: "Registros por mes",
                data: datosLinea.data,
                borderColor: "#764ba2",
                backgroundColor: "rgba(118,75,162,0.15)",
                fill: true,
                tension: 0.3
            }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });
</script>

<?php terminar_pagina(); ?>
