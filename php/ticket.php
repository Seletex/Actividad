<?php
/**
 * Portal Público de Mesa de Ayuda / Radicación y Consulta de Tickets.
 * No requiere inicio de sesión.
 */

define('APP_INICIADA', true);

require __DIR__ . '/config.php';
require __DIR__ . '/lib/util.php';
require __DIR__ . '/lib/db.php';
require __DIR__ . '/lib/auth.php';
require __DIR__ . '/lib/tickets.php';

cabeceras_seguridad();
iniciar_sesion();

// Asegurar que la tabla exista
try {
    db();
    db_instalar_esquema();
} catch (Exception $e) {
    // Si no conecta, se maneja abajo
}

$mensajeExito = '';
$ticketCreado = null;
$error = '';

$dependenciasOficiales = array(
    'ACCION COMUNAL', 'AGRONEGOCIOS', 'ALCALDÍA', 'ALMACEN MUNICIPAL', 'ARCHIVO GENERAL',
    'BIBLIOTECAS', 'CAI OBREROS DE CRISTO', 'CASA DE JUSTICIA', 'CASA DE LA MUJER', 'CATASTRO',
    'CENTRO DEL CUIDADO', 'CENTRO DÍA', 'COMISARÍA DE FAMILIA', 'COMUNICACIONES', 'CONCEJO MUNICIPAL',
    'CONTABILIDAD', 'CONTRATACION', 'CONTROL DISCIPLINARIO', 'CONTROL INTERNO', 'CORREGIDURIA SAN JOSE',
    'CULTURA', 'DESARROLLO COMUNITARIO', 'DESARROLLO ECONOMICO', 'EDUCACION Y CULTURA', 'EDUCACIÓN',
    'EJECUCIONES FISCALES', 'FAMILIA', 'GAULA', 'GESTION HUMANA', 'GESTIÓN PREDIAL', 'GOBIERNO',
    'HACIENDA', 'HOSPITAL DE LA CEJA', 'IMPUESTOS', 'INFRAESTRUCTURA', 'INSPECCIÓN DE POLICÍA',
    'MEDIO AMBIENTE', 'NOMINA', 'OFICINA DE SISTEMAS', 'PARQUE EDUCATIVO', 'PERSONERÍA',
    'PLANEACIÓN', 'PLAZA DE MERCADO', 'PRESUPUESTO', 'PROTECCION SOCIAL', 'PROYECCIÓN SOCIAL',
    'RADIO CAPIRO', 'SAIMYR', 'SALUD', 'SECRETARIA PRIVADA', 'SEGURIDAD Y SALUD EN EL TRABAJO',
    'SIJIN', 'SISBEN', 'TEATRO MUNICIPAL', 'TESORERIA', 'TRÁNSITO Y TRANSPORTE', 'UAI',
    'VENTANILLA ÚNICA', 'VICTIMAS', 'VIVIENDA'
);

$dependencias = array();
$tiposSolicitud = array();
try {
    $depsBd = db_cargar_lista('dependencias');
    $depsReg = db_todo("SELECT DISTINCT dependencia FROM registros WHERE dependencia IS NOT NULL AND dependencia != '' AND dependencia NOT LIKE '2026%' ORDER BY dependencia");
    $listaReg = array();
    foreach ($depsReg as $r) {
        $depVal = trim($r['dependencia']);
        if ($depVal !== '') $listaReg[] = $depVal;
    }
    $dependencias = array_values(array_unique(array_filter(array_merge($dependenciasOficiales, $depsBd, $listaReg))));
    sort($dependencias, SORT_NATURAL | SORT_FLAG_CASE);
} catch (Exception $e) {
    $dependencias = $dependenciasOficiales;
}

$tiposSolicitudPredeterminados = array(
    'Impresoras (Configuración / No imprime / Tóner)',
    'Escáner / Digitalización de documentos',
    'Hardware / Falla en equipo (No enciende / Se apaga / Pantalla)',
    'Mantenimiento Preventivo / Limpieza física',
    'Revisión de Periféricos (Teclado, Mouse, Monitor, Cables)',
    'Red e Internet (Sin conexión / Caída de red / Wi-Fi)',
    'Punto de Red / Conector RJ45 dañado',
    'Telefonía IP / Configuración de Extensión',
    'Software / Instalación o actualización de programas',
    'Microsoft Office (Word, Excel, Outlook / Activación)',
    'Aplicativos Institucionales (SAIMYR, Catastro, SECOP, etc.)',
    'Antivirus / Detección y limpieza de virus',
    'Correo Institucional (Acceso, configuración o fallas)',
    'Cambio o restablecimiento de contraseña',
    'Asignación o retiro de permisos y usuarios',
    'Acceso al Dominio / Carpetas compartidas en servidor',
    'Apoyo técnico en Sala de Juntas / Eventos / Concejo',
    'Configuración de Video Beam / Proyector / Sonido',
    'Préstamo de equipo portátil para comisión o evento',
    'Consulta / Asesoría y acompañamiento tecnológico',
    'Otros requerimientos de soporte TI'
);

$tiposBd = array();
try {
    $tiposBd = db_cargar_lista('tipos_solicitud');
} catch (Exception $e) {}

$tiposSolicitud = array_values(array_unique(array_filter(array_merge($tiposSolicitudPredeterminados, $tiposBd))));

// ---------------------------------------------------------------------------
// Procesar Radicación de Nuevo Ticket
// ---------------------------------------------------------------------------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['accion']) && $_POST['accion'] === 'crear_ticket') {
    if (!csrf_ok()) {
        $error = 'La sesión expiró por inactividad. Por favor intente nuevamente.';
    } else {
        $dep = trim(isset($_POST['dependencia']) ? (string)$_POST['dependencia'] : '');
        $sol = trim(isset($_POST['solicitante']) ? (string)$_POST['solicitante'] : '');
        $tipo = trim(isset($_POST['tipo_solicitud']) ? (string)$_POST['tipo_solicitud'] : '');
        $desc = trim(isset($_POST['descripcion']) ? (string)$_POST['descripcion'] : '');
        $tel = trim(isset($_POST['telefono']) ? (string)$_POST['telefono'] : '');
        $correo = trim(isset($_POST['correo']) ? (string)$_POST['correo'] : '');
        $prio = trim(isset($_POST['prioridad']) ? (string)$_POST['prioridad'] : 'Media');

        if ($dep === '' || $sol === '' || $tipo === '' || $desc === '') {
            $error = 'Por favor complete todos los campos obligatorios (*).';
        } else {
            try {
                $ticketCreado = ticket_crear(array(
                    'dependencia'    => $dep,
                    'solicitante'    => $sol,
                    'tipo_solicitud' => $tipo,
                    'descripcion'    => $desc,
                    'telefono'       => $tel,
                    'correo'         => $correo,
                    'prioridad'      => $prio,
                ));
                $mensajeExito = '¡Su solicitud ha sido radicada exitosamente!';
            } catch (Exception $e) {
                $error = 'Error al registrar la solicitud: ' . $e->getMessage();
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Procesar Consulta de Ticket
// ---------------------------------------------------------------------------
$ticketConsultado = null;
$radicadoBuscado = isset($_GET['radicado']) ? trim((string)$_GET['radicado']) : '';
if ($radicadoBuscado !== '') {
    try {
        $ticketConsultado = ticket_obtener_por_radicado($radicadoBuscado);
        if (!$ticketConsultado && empty($error)) {
            $error = 'No se encontró ninguna solicitud con el radicado: ' . htmlspecialchars($radicadoBuscado);
        }
    } catch (Exception $e) {
        $error = 'Error al consultar el radicado: ' . $e->getMessage();
    }
}

$pestanaActiva = ($radicadoBuscado !== '' || isset($_GET['consultar'])) ? 'consultar' : 'radicar';
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mesa de Ayuda - Solicitudes de Soporte TI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f4f6f9;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header-mesa {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 35px 0 25px 0;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .card-custom {
            border: none;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.06);
            background: white;
        }
        .nav-pills .nav-link {
            border-radius: 8px;
            padding: 10px 20px;
            font-weight: 500;
            color: #495057;
        }
        .nav-pills .nav-link.active {
            background-color: #2a5298;
            color: white;
        }
        .badge-estado-pendiente { background-color: #ffc107; color: #000; font-size: 0.95rem; }
        .badge-estado-en_proceso { background-color: #0dcaf0; color: #000; font-size: 0.95rem; }
        .badge-estado-resuelto { background-color: #198754; color: #fff; font-size: 0.95rem; }
        .badge-prioridad-alta { background-color: #dc3545; color: #fff; }
        .badge-prioridad-urgente { background-color: #842029; color: #fff; }
        .radicado-box {
            background: #e8f4fd;
            border: 2px dashed #2a5298;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
        }
    </style>
</head>
<body>

<header class="header-mesa">
    <div class="container">
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
            <div>
                <h1 class="h3 mb-1"><i class="fas fa-headset me-2"></i> Mesa de Ayuda TI</h1>
                <p class="mb-0 text-white-50">Portal de Solicitudes y Soporte Técnico</p>
            </div>
            <div>
                <a href="index.php" class="btn btn-outline-light btn-sm">
                    <i class="fas fa-user-shield me-1"></i> Acceso Técnicos
                </a>
            </div>
        </div>
    </div>
</header>

<main class="container my-4 flex-grow-1">
    <?php if ($error !== ''): ?>
        <div class="alert alert-danger alert-dismissible fade show" role="alert">
            <i class="fas fa-exclamation-circle me-2"></i> <?php echo e($error); ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    <?php endif; ?>

    <!-- Pestañas de navegación -->
    <ul class="nav nav-pills mb-4 justify-content-center" id="pills-tab" role="tablist">
        <li class="nav-item" role="presentation">
            <button class="nav-link <?php echo $pestanaActiva === 'radicar' ? 'active' : ''; ?>" id="pills-radicar-tab" data-bs-toggle="pill" data-bs-target="#pills-radicar" type="button" role="tab">
                <i class="fas fa-plus-circle me-1"></i> Radicar Solicitud
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link <?php echo $pestanaActiva === 'consultar' ? 'active' : ''; ?>" id="pills-consultar-tab" data-bs-toggle="pill" data-bs-target="#pills-consultar" type="button" role="tab">
                <i class="fas fa-search me-1"></i> Consultar Estado
            </button>
        </li>
    </ul>

    <div class="tab-content" id="pills-tabContent">
        <!-- PESTAÑA 1: RADICAR SOLICITUD -->
        <div class="tab-pane fade <?php echo $pestanaActiva === 'radicar' ? 'show active' : ''; ?>" id="pills-radicar" role="tabpanel">
            <?php if ($ticketCreado): ?>
                <div class="card card-custom p-4 mb-4 text-center">
                    <div class="text-success mb-3">
                        <i class="fas fa-check-circle fa-4x"></i>
                    </div>
                    <h3 class="text-success">¡Solicitud Radicada con Éxito!</h3>
                    <p class="text-muted">El equipo de soporte ha sido notificado y atenderá su caso a la brevedad.</p>

                    <div class="radicado-box my-3 mx-auto" style="max-width: 450px;">
                        <span class="text-muted d-block small">SU NÚMERO DE RADICADO ES:</span>
                        <h2 class="text-primary mb-1 fw-bold"><?php echo e($ticketCreado['radicado']); ?></h2>
                        <small class="text-muted">Guarde este número para consultar el avance de su solicitud.</small>
                    </div>

                    <div class="mt-3">
                        <a href="ticket.php?radicado=<?php echo urlencode($ticketCreado['radicado']); ?>" class="btn btn-primary me-2">
                            <i class="fas fa-eye me-1"></i> Ver Estado de mi Solicitud
                        </a>
                        <a href="ticket.php" class="btn btn-outline-secondary">
                            <i class="fas fa-plus me-1"></i> Radicar Otra Solicitud
                        </a>
                    </div>
                </div>
            <?php else: ?>
                <div class="row justify-content-center">
                    <div class="col-lg-8">
                        <div class="card card-custom p-4">
                            <h4 class="mb-3 text-primary"><i class="fas fa-file-alt me-2"></i> Formulario de Solicitud</h4>
                            <p class="text-muted small mb-4">Complete la información a continuación para que el equipo técnico pueda atender su requerimiento oportunamente.</p>

                            <form action="ticket.php" method="POST">
                                <?php echo csrf_campo(); ?>
                                <input type="hidden" name="accion" value="crear_ticket">

                                <div class="row g-3">
                                    <div class="col-md-6">
                                        <label class="form-label fw-bold">Ubicación / Dependencia *</label>
                                        <div class="input-group">
                                            <span class="input-group-text bg-light"><i class="fas fa-building text-muted"></i></span>
                                            <input type="text" name="dependencia" list="lista-dependencias" class="form-control" placeholder="Escriba o seleccione su ubicación..." required autocomplete="off">
                                        </div>
                                        <datalist id="lista-dependencias">
                                            <?php foreach ($dependencias as $dep): ?>
                                                <option value="<?php echo e($dep); ?>">
                                            <?php endforeach; ?>
                                        </datalist>
                                        <div class="form-text text-muted small" style="font-size: 0.78rem;">
                                            <i class="fas fa-search me-1"></i> Puede buscar escribiendo o digitar una nueva ubicación si no está en la lista.
                                        </div>
                                    </div>

                                    <div class="col-md-6">
                                        <label class="form-label fw-bold">Nombre del Solicitante *</label>
                                        <input type="text" name="solicitante" class="form-control" placeholder="Ej: Carlos Pérez" required maxlength="150">
                                    </div>

                                    <div class="col-md-6">
                                        <label class="form-label fw-bold">Tipo de Solicitud *</label>
                                        <div class="input-group">
                                            <span class="input-group-text bg-light"><i class="fas fa-tools text-muted"></i></span>
                                            <input type="text" name="tipo_solicitud" list="lista-tipos" class="form-control" placeholder="Escriba o seleccione el tipo de soporte..." required autocomplete="off">
                                        </div>
                                        <datalist id="lista-tipos">
                                            <?php foreach ($tiposSolicitud as $tipo): ?>
                                                <option value="<?php echo e($tipo); ?>">
                                            <?php endforeach; ?>
                                        </datalist>
                                        <div class="form-text text-muted small" style="font-size: 0.78rem;">
                                            <i class="fas fa-search me-1"></i> Puede buscar en la lista o escribir uno nuevo si no aparece.
                                        </div>
                                    </div>

                                    <div class="col-md-6">
                                        <label class="form-label fw-bold">Prioridad</label>
                                        <select name="prioridad" class="form-select">
                                            <option value="Baja">Baja (Requerimiento general sin urgencia)</option>
                                            <option value="Media" selected>Media (Atención estándar)</option>
                                            <option value="Alta">Alta (Afecta operaciones del área)</option>
                                            <option value="Urgente">Urgente (Servicio completamente caído)</option>
                                        </select>
                                    </div>

                                    <div class="col-md-6">
                                        <label class="form-label">Teléfono / Celular / Extensión</label>
                                        <div class="input-group">
                                            <span class="input-group-text"><i class="fas fa-phone"></i></span>
                                            <input type="text" name="telefono" class="form-control" placeholder="Para contacto directo" maxlength="50">
                                        </div>
                                    </div>

                                    <div class="col-md-6">
                                        <label class="form-label">Correo Electrónico (Opcional)</label>
                                        <div class="input-group">
                                            <span class="input-group-text"><i class="fas fa-envelope"></i></span>
                                            <input type="email" name="correo" class="form-control" placeholder="Para notificaciones" maxlength="150">
                                        </div>
                                    </div>

                                    <div class="col-12">
                                        <label class="form-label fw-bold">Descripción detallada del problema o necesidad *</label>
                                        <textarea name="descripcion" class="form-control" rows="4" placeholder="Describa claramente qué está sucediendo, mensaje de error si lo hay, número de equipo o cualquier detalle útil..." required></textarea>
                                    </div>

                                    <div class="col-12 text-end mt-4">
                                        <button type="submit" class="btn btn-primary btn-lg px-4">
                                            <i class="fas fa-paper-plane me-1"></i> Enviar Solicitud
                                        </button>
                                    </div>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            <?php endif; ?>
        </div>

        <!-- PESTAÑA 2: CONSULTAR ESTADO -->
        <div class="tab-pane fade <?php echo $pestanaActiva === 'consultar' ? 'show active' : ''; ?>" id="pills-consultar" role="tabpanel">
            <div class="row justify-content-center">
                <div class="col-lg-8">
                    <div class="card card-custom p-4 mb-4">
                        <h4 class="mb-3 text-primary"><i class="fas fa-search me-2"></i> Consultar Estado de Solicitud</h4>
                        <form action="ticket.php" method="GET" class="row g-2 align-items-center">
                            <input type="hidden" name="consultar" value="1">
                            <div class="col-sm-9">
                                <div class="input-group input-group-lg">
                                    <span class="input-group-text bg-white"><i class="fas fa-ticket-alt text-primary"></i></span>
                                    <input type="text" name="radicado" class="form-control text-uppercase" placeholder="Ingrese número de radicado (Ej: TK-202611-0042)" value="<?php echo e($radicadoBuscado); ?>" required>
                                </div>
                            </div>
                            <div class="col-sm-3">
                                <button type="submit" class="btn btn-primary btn-lg w-100">
                                    <i class="fas fa-search me-1"></i> Buscar
                                </button>
                            </div>
                        </form>
                    </div>

                    <?php if ($ticketConsultado): ?>
                        <?php
                            $estado = $ticketConsultado['estado'];
                            $claseEstado = 'badge-estado-pendiente';
                            $iconoEstado = 'clock';
                            if ($estado === 'En proceso') {
                                $claseEstado = 'badge-estado-en_proceso';
                                $iconoEstado = 'tools';
                            } elseif ($estado === 'Resuelto') {
                                $claseEstado = 'badge-estado-resuelto';
                                $iconoEstado = 'check-circle';
                            }
                        ?>
                        <div class="card card-custom p-4">
                            <div class="d-flex justify-content-between align-items-center flex-wrap pb-3 mb-3 border-bottom gap-2">
                                <div>
                                    <span class="text-muted small d-block">RADICADO</span>
                                    <h3 class="text-primary mb-0 fw-bold"><?php echo e($ticketConsultado['radicado']); ?></h3>
                                </div>
                                <div>
                                    <span class="badge <?php echo $claseEstado; ?> p-2 px-3">
                                        <i class="fas fa-<?php echo $iconoEstado; ?> me-1"></i> <?php echo e($estado); ?>
                                    </span>
                                </div>
                            </div>

                            <div class="row g-3 mb-3">
                                <div class="col-sm-6">
                                    <small class="text-muted d-block">Dependencia</small>
                                    <strong><?php echo e($ticketConsultado['dependencia']); ?></strong>
                                </div>
                                <div class="col-sm-6">
                                    <small class="text-muted d-block">Solicitante</small>
                                    <strong><?php echo e($ticketConsultado['solicitante']); ?></strong>
                                </div>
                                <div class="col-sm-6">
                                    <small class="text-muted d-block">Tipo de Soporte</small>
                                    <span><?php echo e($ticketConsultado['tipo_solicitud']); ?></span>
                                </div>
                                <div class="col-sm-6">
                                    <small class="text-muted d-block">Fecha de Radicación</small>
                                    <span><?php echo e($ticketConsultado['fecha_creacion']); ?></span>
                                </div>
                                <div class="col-sm-6">
                                    <small class="text-muted d-block">Técnico Asignado</small>
                                    <?php if (!empty($ticketConsultado['tecnico_asignado'])): ?>
                                        <span class="badge bg-secondary"><i class="fas fa-user-cog me-1"></i> <?php echo e($ticketConsultado['tecnico_asignado']); ?></span>
                                    <?php else: ?>
                                        <span class="text-muted fst-italic">Pendiente de asignación</span>
                                    <?php endif; ?>
                                </div>
                                <div class="col-sm-6">
                                    <small class="text-muted d-block">Prioridad</small>
                                    <span class="badge bg-light text-dark border"><?php echo e($ticketConsultado['prioridad']); ?></span>
                                </div>
                            </div>

                            <div class="mb-3">
                                <small class="text-muted d-block mb-1">Descripción del requerimiento:</small>
                                <div class="p-3 bg-light rounded border">
                                    <?php echo nl2br(e($ticketConsultado['descripcion'])); ?>
                                </div>
                            </div>

                            <?php if ($estado === 'Resuelto'): ?>
                                <div class="alert alert-success mt-2 mb-0">
                                    <h6 class="alert-heading mb-1"><i class="fas fa-check-circle me-1"></i> Solución Brindada:</h6>
                                    <p class="mb-2"><?php echo nl2br(e($ticketConsultado['solucion'])); ?></p>
                                    <small class="text-muted d-block border-top pt-1 mt-1">
                                        Fecha de cierre: <?php echo e($ticketConsultado['fecha_cierre']); ?>
                                        <?php
                                            $colabs = json_decode((string)$ticketConsultado['tecnicos_colaboradores'], true);
                                            if (!empty($colabs) && is_array($colabs)) {
                                                echo " | Técnicos colaboradores: " . e(implode(', ', $colabs));
                                            }
                                        ?>
                                    </small>
                                </div>
                            <?php endif; ?>
                        </div>
                    <?php endif; ?>
                </div>
            </div>
        </div>
    </div>
</main>

<footer class="bg-white border-top py-3 text-center text-muted small mt-auto">
    <div class="container">
        Sistema de Actividades & Mesa de Ayuda TI &copy; <?php echo date('Y'); ?>
    </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
