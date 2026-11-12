<?php
/**
 * Panel de configuración: catálogos, usuarios, datos del contrato y respaldos.
 *
 * @var array $contrato
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

$usuario = usuario_actual();
$admin = es_admin();
iniciar_pagina('Mi Gestión', 'gestion', 'cog');

$contrato = isset($contrato) ? $contrato : array();
$valor_contrato = function ($clave) use ($contrato) {
    return isset($contrato[$clave]) ? (string)$contrato[$clave] : '';
};
?>

<div class="row">
    <div class="col-lg-7">
        <div class="card">
            <div class="card-header">
                <h5><i class="fas fa-tasks text-primary me-2"></i> Gestión de Actividades</h5>
            </div>
            <div class="card-body">
                <?php if ($admin): ?>
                    <h6 class="text-uppercase text-muted fw-bold mb-3 small">🌐 Actividades globales</h6>
                    <form action="<?php echo e(url('agregar_actividad_global')); ?>" method="POST" class="row g-2 mb-3">
                        <?php echo csrf_campo(); ?>
                        <div class="col-md-9">
                            <input type="text" name="nuevo_item" class="form-control"
                                   placeholder="Nueva actividad global…" maxlength="200" required>
                        </div>
                        <div class="col-md-3">
                            <button class="btn btn-outline-primary w-100">Añadir</button>
                        </div>
                    </form>
                    <div class="list-group mb-4">
                        <?php foreach (db_cargar_lista('actividad') as $item): ?>
                            <div class="list-group-item d-flex justify-content-between align-items-center py-2">
                                <span><?php echo e($item); ?></span>
                                <form action="<?php echo e(url('eliminar_actividad_global')); ?>" method="POST"
                                      onsubmit="return confirm('¿Eliminar esta actividad global?')">
                                    <?php echo csrf_campo(); ?>
                                    <input type="hidden" name="actividad" value="<?php echo e($item); ?>">
                                    <button class="btn btn-sm btn-outline-danger border-0"><i class="fas fa-trash-alt"></i></button>
                                </form>
                            </div>
                        <?php endforeach; ?>
                    </div>

                    <?php
                    $catalogos = array(
                        'ubicacion' => array('Ubicaciones', 'agregar_ubicacion', 'eliminar_ubicacion', 'ubicacion'),
                        'tipo_solicitud' => array('Tipos de solicitud', 'agregar_tipo_solicitud', 'eliminar_tipo_solicitud', 'tipo'),
                        'medio_solicitud' => array('Medios de solicitud', 'agregar_medio_solicitud', 'eliminar_medio_solicitud', 'medio'),
                    );
                    ?>
                    <?php foreach ($catalogos as $tipo => $datos): ?>
                        <?php $items = db_cargar_lista($tipo); ?>
                        <h6 class="text-uppercase text-muted fw-bold mb-3 small">📋 <?php echo e($datos[0]); ?> (<?php echo count($items); ?>)</h6>
                        <form action="<?php echo e(url($datos[1])); ?>" method="POST" class="row g-2 mb-2">
                            <?php echo csrf_campo(); ?>
                            <div class="col-md-9">
                                <input type="text" name="nuevo_item" class="form-control"
                                       placeholder="Agregar <?php echo e(minusculas($datos[0])); ?>…" maxlength="120" required>
                            </div>
                            <div class="col-md-3">
                                <button class="btn btn-outline-primary w-100">Añadir</button>
                            </div>
                        </form>
                        <div class="list-group mb-4" style="max-height:260px;overflow:auto;">
                            <?php foreach ($items as $item): ?>
                                <div class="list-group-item d-flex justify-content-between align-items-center py-2">
                                    <span class="small"><?php echo e($item); ?></span>
                                    <form action="<?php echo e(url($datos[2])); ?>" method="POST"
                                          onsubmit="return confirm('¿Eliminar este valor?')">
                                        <?php echo csrf_campo(); ?>
                                        <input type="hidden" name="<?php echo e($datos[3]); ?>" value="<?php echo e($item); ?>">
                                        <button class="btn btn-sm btn-outline-danger border-0"><i class="fas fa-trash-alt"></i></button>
                                    </form>
                                </div>
                            <?php endforeach; ?>
                        </div>
                    <?php endforeach; ?>
                <?php endif; ?>

                <h6 class="text-uppercase text-muted fw-bold mb-3 small">✨ Mis Actividades Propias</h6>

                <?php if (!$admin): ?>
                    <div class="card mb-4 border-info">
                        <div class="card-header bg-info text-white">
                            <h6 class="mb-0"><i class="fas fa-file-excel me-2"></i> Registrar varias actividades de una vez</h6>
                        </div>
                        <div class="card-body">
                            <p class="text-muted small mb-3">
                                Descarga el Excel con las actividades de tu contrato que aún no tienen registro,
                                llénalas y vuelve a subirlo. Se guardan todas juntas, con tu usuario.
                            </p>
                            <a href="<?php echo e(url('descargar_pendientes')); ?>" class="btn btn-outline-info btn-sm mb-2">
                                <i class="fas fa-download me-1"></i> Descargar Excel con mis pendientes
                            </a>
                            <form action="<?php echo e(url('importar_mis_actividades')); ?>" method="POST"
                                  enctype="multipart/form-data" class="row g-2">
                                <?php echo csrf_campo(); ?>
                                <div class="col-md-8">
                                    <input type="file" name="archivo" accept=".xlsx" required class="form-control form-control-sm">
                                </div>
                                <div class="col-md-4">
                                    <button class="btn btn-info btn-sm w-100">
                                        <i class="fas fa-upload me-1"></i> Subir Excel
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                <?php endif; ?>

                <form action="<?php echo e(url('agregar_actividad_personal')); ?>" method="POST" class="row g-2 mb-4">
                    <?php echo csrf_campo(); ?>
                    <div class="col-md-9">
                        <input type="text" name="nueva_actividad" class="form-control"
                               placeholder="Agrega algo específico de tu cargo…" maxlength="500" required>
                    </div>
                    <div class="col-md-3">
                        <button class="btn btn-outline-primary w-100">Añadir</button>
                    </div>
                </form>

                <?php
                $mis_actividades = $admin ? array() : db_cargar_actividades($usuario);
                if ($admin): ?>
                    <p class="text-muted small">El administrador no tiene actividades propias de registro.</p>
                <?php elseif (empty($mis_actividades)): ?>
                    <p class="text-muted small">Todavía no ha agregado actividades propias.</p>
                <?php else: ?>
                    <div class="list-group shadow-sm rounded-3">
                        <?php foreach ($mis_actividades as $item): ?>
                            <div class="list-group-item d-flex justify-content-between align-items-center">
                                <span class="small"><?php echo e($item); ?></span>
                                <form action="<?php echo e(url('eliminar_actividad_personal')); ?>" method="POST"
                                      onsubmit="return confirm('¿Quitar esta actividad de su lista?')">
                                    <?php echo csrf_campo(); ?>
                                    <input type="hidden" name="actividad" value="<?php echo e($item); ?>">
                                    <button class="btn btn-sm btn-outline-danger border-0"><i class="fas fa-trash-alt"></i></button>
                                </form>
                            </div>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
            </div>
        </div>
    </div>

    <div class="col-lg-5">
        <?php if ($admin): ?>
            <div class="card">
                <div class="card-header">
                    <h5><i class="fas fa-users-cog text-primary me-2"></i> Usuarios del Sistema</h5>
                </div>
                <div class="card-body">
                    <form action="<?php echo e(url('agregar_usuario')); ?>" method="POST" class="row g-2 mb-3">
                        <?php echo csrf_campo(); ?>
                        <div class="col-md-9">
                            <input type="text" name="nuevo_usuario" class="form-control"
                                   placeholder="Nuevo usuario…" maxlength="50" required>
                        </div>
                        <div class="col-md-3">
                            <button class="btn btn-outline-primary w-100">Añadir</button>
                        </div>
                    </form>
                    <div class="list-group">
                        <?php foreach (db_cargar_usuarios() as $cuenta): ?>
                            <?php
                            $fila_usuario = db_uno(
                                "SELECT debe_cambiar_contrasena, password_hash FROM usuarios WHERE username = ?",
                                array($cuenta)
                            );
                            $pendiente_clave = !empty($fila_usuario['debe_cambiar_contrasena']);
                            ?>
                            <div class="list-group-item py-3">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <span class="fw-bold"><?php echo e($cuenta); ?></span>
                                        <?php if ($cuenta === 'admin'): ?>
                                            <span class="badge bg-primary">Admin</span>
                                        <?php endif; ?>
                                        <?php if ($pendiente_clave): ?>
                                            <span class="badge bg-warning text-dark">debe cambiar clave</span>
                                        <?php endif; ?>
                                        <?php if (empty($fila_usuario['password_hash'])): ?>
                                            <span class="badge bg-secondary">sin contraseña</span>
                                        <?php endif; ?>
                                    </div>
                                    <?php if ($cuenta !== 'admin'): ?>
                                        <form action="<?php echo e(url('eliminar_usuario')); ?>" method="POST"
                                              onsubmit="return confirm('¿Eliminar el usuario <?php echo e($cuenta); ?>?')">
                                            <?php echo csrf_campo(); ?>
                                            <input type="hidden" name="usuario" value="<?php echo e($cuenta); ?>">
                                            <button class="btn btn-sm btn-outline-danger border-0"><i class="fas fa-user-minus"></i></button>
                                        </form>
                                    <?php endif; ?>
                                </div>
                                <form action="<?php echo e(url('asignar_contrasena')); ?>" method="POST" class="row g-1 mt-2">
                                    <?php echo csrf_campo(); ?>
                                    <input type="hidden" name="usuario" value="<?php echo e($cuenta); ?>">
                                    <div class="col-6">
                                        <input type="password" name="nueva_contrasena" class="form-control form-control-sm"
                                               placeholder="Nueva clave" minlength="6" required>
                                    </div>
                                    <div class="col-4">
                                        <div class="form-check small mt-1">
                                            <input class="form-check-input" type="checkbox" name="forzar_cambio"
                                                   value="1" id="forzar_<?php echo e($cuenta); ?>">
                                            <label class="form-check-label" for="forzar_<?php echo e($cuenta); ?>">forzar cambio</label>
                                        </div>
                                    </div>
                                    <div class="col-2">
                                        <button class="btn btn-sm btn-outline-primary w-100" title="Asignar contraseña">
                                            <i class="fas fa-key"></i>
                                        </button>
                                    </div>
                                </form>
                            </div>
                        <?php endforeach; ?>
                    </div>
                </div>
            </div>
        <?php endif; ?>

        <?php if ($admin): ?>
            <div class="card mt-3 border-info">
                <div class="card-header bg-info text-white">
                    <h5 class="mb-0"><i class="fas fa-users-cog me-2"></i> Sincronizar usuarios y configuraciones</h5>
                </div>
                <div class="card-body">
                    <p class="small mb-3">
                        Carga usuarios, actividades personales y datos de contrato desde un
                        archivo <code>usuarios.json</code>. Las contraseñas existentes no se modifican.
                    </p>
                    <form action="<?php echo e(url('sincronizar_usuarios')); ?>" method="POST"
                          enctype="multipart/form-data">
                        <?php echo csrf_campo(); ?>
                        <input type="file" name="archivo" class="form-control form-control-sm mb-2" accept=".json">
                        <button type="submit" class="btn btn-info btn-sm">
                            <i class="fas fa-sync-alt me-1"></i> Sincronizar datos de usuarios
                        </button>
                    </form>
                </div>
            </div>
        <?php endif; ?>

        <div class="card mt-3">
            <div class="card-header">
                <h5><i class="fas fa-file-signature text-primary me-2"></i> Datos del Contrato</h5>
            </div>
            <div class="card-body">
                <form action="<?php echo e(url('guardar_datos_contrato')); ?>" method="POST">
                    <?php echo csrf_campo(); ?>
                    <div class="mb-2">
                        <label class="form-label small">Número de Contrato</label>
                        <input type="text" name="nro" value="<?php echo e($valor_contrato('nro')); ?>" class="form-control">
                    </div>
                    <div class="mb-2">
                        <label class="form-label small">Objeto</label>
                        <input type="text" name="objeto" value="<?php echo e($valor_contrato('objeto')); ?>" class="form-control">
                    </div>
                    <div class="mb-2">
                        <label class="form-label small">Nombre Contratista</label>
                        <input type="text" name="nombre" value="<?php echo e($valor_contrato('nombre')); ?>" class="form-control">
                    </div>
                    <div class="mb-2">
                        <label class="form-label small">Cédula</label>
                        <input type="text" name="cedula" value="<?php echo e($valor_contrato('cedula')); ?>" class="form-control">
                    </div>
                    <div class="mb-2">
                        <label class="form-label small">Supervisor</label>
                        <input type="text" name="supervisor" value="<?php echo e($valor_contrato('supervisor')); ?>" class="form-control">
                    </div>
                    <div class="d-grid mt-3">
                        <button class="btn btn-primary">Guardar Datos del Contrato</button>
                    </div>
                </form>
            </div>
        </div>

        <div class="card mt-3">
            <div class="card-header">
                <h5><i class="fas fa-shield-alt text-primary me-2"></i> Seguridad</h5>
            </div>
            <div class="card-body">
                <div class="d-grid gap-2">
                    <a href="<?php echo e(url('cambiar_contrasena')); ?>" class="btn btn-outline-primary">
                        <i class="fas fa-key me-1"></i> Cambiar mi contraseña
                    </a>
                    <?php if ($admin): ?>
                        <a href="<?php echo e(url('sesiones')); ?>" class="btn btn-outline-primary">
                            <i class="fas fa-user-clock me-1"></i> Sesiones activas
                        </a>
                        <a href="<?php echo e(url('auditoria')); ?>" class="btn btn-outline-primary">
                            <i class="fas fa-clipboard-list me-1"></i> Ver auditoría
                        </a>
                        <form action="<?php echo e(url('descargar_respaldo')); ?>" method="POST">
                            <?php echo csrf_campo(); ?>
                            <button class="btn btn-outline-success w-100">
                                <i class="fas fa-download me-1"></i> Descargar respaldo completo (ZIP)
                            </button>
                        </form>
                    <?php endif; ?>
                </div>
            </div>
        </div>

        <div class="card mt-3 text-white" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <div class="card-body text-center py-4">
                <i class="fas fa-info-circle fa-3x mb-3 opacity-50"></i>
                <h5>Ayuda del Sistema</h5>
                <p class="small mb-0">
                    Los cambios en actividades globales afectan a todos los usuarios.
                    Las actividades personales son privadas para cada cuenta.
                </p>
            </div>
        </div>
    </div>
</div>

<?php terminar_pagina(); ?>
