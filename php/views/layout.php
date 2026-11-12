<?php
/**
 * Plantilla general: cabecera, barra superior, menú lateral y cierre.
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

function menu_lateral($activo)
{
    $enlaces = array(
        'inicio' => array('Inicio', 'fa-home'),
        'tickets' => array('Mesa de Ayuda', 'fa-headset'),
        'listado' => array('Mis Actividades', 'fa-list'),
        'gestion' => array('Mi Gestión', 'fa-cog'),
        'estadisticas' => array('Estadísticas', 'fa-chart-line'),
        'exportar' => array('Exportar', 'fa-file-export'),
    );
    $html = '<div class="col-md-2 sidebar d-none d-md-block"><div class="pt-4">'
        . '<div class="list-group list-group-flush">';
    $pendientesTickets = function_exists('ticket_conteo_pendientes') ? ticket_conteo_pendientes() : 0;
    foreach ($enlaces as $ruta => $datos) {
        $clase = ($activo === $ruta) ? ' active' : '';
        $badge = '';
        if ($ruta === 'tickets' && $pendientesTickets > 0) {
            $badge = ' <span class="badge bg-danger rounded-pill float-end">' . $pendientesTickets . '</span>';
        }
        $html .= '<a href="' . e(url($ruta)) . '" class="list-group-item list-group-item-action'
            . $clase . '"><i class="fas ' . $datos[1] . ' me-2 text-primary"></i> '
            . e($datos[0]) . $badge . '</a>';
    }
    if (es_admin()) {
        $clase = ($activo === 'sesiones') ? ' active' : '';
        $html .= '<a href="' . e(url('sesiones')) . '" class="list-group-item list-group-item-action'
            . $clase . '"><i class="fas fa-user-clock me-2 text-primary"></i> Sesiones</a>';
        $clase = ($activo === 'auditoria') ? ' active' : '';
        $html .= '<a href="' . e(url('auditoria')) . '" class="list-group-item list-group-item-action'
            . $clase . '"><i class="fas fa-clipboard-list me-2 text-primary"></i> Auditoría</a>';
    }
    $html .= '</div></div></div>';
    return $html;
}

function iniciar_pagina($titulo, $activo = '', $icono = 'tasks')
{
    $usuario = usuario_actual();
    $alertas = '';
    foreach (mensajes_de_url() as $mensaje) {
        $alertas .= '<div class="alert alert-' . e($mensaje['tipo'])
            . ' alert-dismissible fade show">' . e($mensaje['texto'])
            . '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>';
    }

    echo '<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>' . e($titulo) . ' - Sistema de Actividades</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" rel="stylesheet" />
    <link href="https://cdn.jsdelivr.net/npm/select2-bootstrap-5-theme@1.3.0/dist/select2-bootstrap-5-theme.min.css" rel="stylesheet" />
    <style>
        .navbar-custom { background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .sidebar { background: #f8f9fa; border-right: 1px solid #dee2e6; height: 100vh; position: fixed; width: 250px; z-index: 1000; }
        .main-content { padding: 30px; background: #f0f2f5; min-height: calc(100vh - 56px); transition: all 0.3s; }
        @media (min-width: 768px) { .main-content { margin-left: 250px; } }
        @media (max-width: 767px) {
            .sidebar { display: none !important; }
            .main-content { margin-left: 0 !important; padding: 15px; }
            .navbar-brand { font-size: 1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 180px; }
            h2 { font-size: 1.4rem; }
            h3 { font-size: 1.2rem; }
        }
        .card { border: none; border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); margin-bottom: 25px; }
        .card-header { background: white; border-bottom: 1px solid #f0f0f0; border-radius: 15px 15px 0 0 !important; padding: 15px 20px; }
        .card-header h5 { margin: 0; color: #4a5568; font-weight: 700; }
        .form-control, .form-select { border-radius: 10px; padding: 10px 12px; border: 1px solid #e2e8f0; }
        .form-control:focus, .form-select:focus { box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1); border-color: #667eea; }
        .btn-action { border-radius: 8px; padding: 8px 16px; font-weight: 600; }
        .list-group-item { border: none; border-bottom: 1px solid #f8f9fa; padding: 15px 20px; }
        .list-group-item:hover { background: #f8fafc; }
        .list-group-item.active { background: #eef2ff; color: #4338ca; border-color: #eef2ff; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark navbar-custom sticky-top">
        <div class="container-fluid">
            <span class="navbar-brand fw-bold mb-0"><i class="fas fa-' . e($icono) . ' me-2"></i> Sistema de Actividades</span>
            <button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#navbarContent">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarContent">
                <ul class="navbar-nav d-md-none mt-3 mb-2 border-top border-light pt-3">
                    <li class="nav-item"><a class="nav-link text-white" href="' . e(url('inicio')) . '"><i class="fas fa-home me-2"></i> Inicio</a></li>
                    <li class="nav-item"><a class="nav-link text-white" href="' . e(url('listado')) . '"><i class="fas fa-list me-2"></i> Mis Actividades</a></li>
                    <li class="nav-item"><a class="nav-link text-white" href="' . e(url('gestion')) . '"><i class="fas fa-cog me-2"></i> Mi Gestión</a></li>
                    <li class="nav-item"><a class="nav-link text-white" href="' . e(url('estadisticas')) . '"><i class="fas fa-chart-line me-2"></i> Estadísticas</a></li>
                    <li class="nav-item"><a class="nav-link text-white" href="' . e(url('exportar')) . '"><i class="fas fa-file-export me-2"></i> Exportar</a></li>
                </ul>
                <div class="ms-auto d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2 mt-3 mt-md-0">
                    <span class="badge bg-white text-dark py-2 px-3 rounded-pill shadow-sm">
                        <i class="fas fa-user-circle me-1 text-primary"></i> ' . e($usuario) . '
                    </span>
                    <div class="d-flex gap-2">
                        <a class="btn btn-sm btn-outline-light px-3 rounded-pill" href="' . e(url('inicio')) . '"><i class="fas fa-home me-1"></i> Inicio</a>
                        <a class="btn btn-sm btn-outline-light px-3 rounded-pill" href="' . e(url('logout')) . '"><i class="fas fa-sign-out-alt me-1"></i> Salir</a>
                    </div>
                </div>
            </div>
        </div>
    </nav>
    <div class="container-fluid p-0">
        <div class="row g-0">
            ' . menu_lateral($activo) . '
            <div class="col-md-10 main-content">
                <div class="container-fluid">
                    ' . $alertas;
}

function terminar_pagina()
{
    echo '
                </div>
            </div>
        </div>
    </div>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/i18n/es.js"></script>
    <script>
        $(document).ready(function() {
            $("select.form-select").each(function() {
                if ($(this).find("option").length > 3) {
                    $(this).select2({ theme: "bootstrap-5", width: "100%", language: "es" });
                }
            });
        });
    </script>
</body>
</html>';
}
