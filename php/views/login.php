<?php
/**
 * Página de acceso. Se muestra cuando no hay sesión iniciada.
 */

if (!defined('APP_INICIADA')) {
    http_response_code(403);
    exit('Acceso no permitido');
}

$error = isset($error) ? $error : '';
$mensaje = isset($mensaje) ? $mensaje : '';
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iniciar Sesión - Sistema de Actividades</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        }
        .login-container {
            width: 100%;
            max-width: 420px;
            margin: 20px;
            background: white;
            padding: 35px 30px;
            border-radius: 16px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
        }
        .form-control {
            border-radius: 8px;
            padding: 10px 14px;
        }
        .btn-ticket {
            background: #f0f7ff;
            color: #1e3c72;
            border: 2px solid #2a5298;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .btn-ticket:hover {
            background: #2a5298;
            color: white;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="login-container">
            <!-- Acceso a Mesa de Ayuda para funcionarios sin login -->
            <div class="text-center mb-4">
                <a href="ticket.php" class="btn btn-ticket w-100 py-2 d-flex align-items-center justify-content-center gap-2">
                    <i class="fas fa-headset fa-lg text-primary"></i>
                    <span>Portal Mesa de Ayuda (Tickets)</span>
                </a>
                <small class="text-muted d-block mt-1">Radicar o consultar solicitudes de soporte TI</small>
            </div>

            <div class="position-relative my-4">
                <hr>
                <span class="position-absolute top-50 start-50 translate-middle bg-white px-3 text-muted small fw-bold">
                    O INGRESO DE TÉCNICOS
                </span>
            </div>

            <h4 class="text-center mb-3 text-dark fw-bold">
                <i class="fas fa-user-shield text-primary me-2"></i> Iniciar Sesión
            </h4>

            <?php if ($error !== ''): ?>
                <div class="alert alert-danger py-2 small"><?php echo e($error); ?></div>
            <?php endif; ?>
            <?php if ($mensaje !== ''): ?>
                <div class="alert alert-success py-2 small"><?php echo e($mensaje); ?></div>
            <?php endif; ?>

            <form action="<?php echo e(url('login')); ?>" method="POST">
                <?php echo csrf_campo(); ?>
                <div class="mb-3">
                    <label for="usuario" class="form-label small fw-bold text-muted">Usuario:</label>
                    <div class="input-group">
                        <span class="input-group-text bg-light"><i class="fas fa-user text-muted"></i></span>
                        <input type="text" id="usuario" name="usuario" class="form-control"
                               autocomplete="username" required autofocus placeholder="Nombre de usuario">
                    </div>
                </div>
                <div class="mb-3">
                    <label for="contrasena" class="form-label small fw-bold text-muted">Contraseña:</label>
                    <div class="input-group">
                        <span class="input-group-text bg-light"><i class="fas fa-lock text-muted"></i></span>
                        <input type="password" id="contrasena" name="contrasena" class="form-control"
                               autocomplete="current-password" required placeholder="••••••••">
                    </div>
                </div>
                <div class="d-grid mt-4">
                    <button type="submit" class="btn btn-primary btn-lg fw-bold">
                        <i class="fas fa-sign-in-alt me-1"></i> Entrar
                    </button>
                </div>
            </form>

            <p class="text-center text-muted small mt-4 mb-0" style="font-size: 0.8rem;">
                Sistema de Gestión de Actividades &copy; <?php echo date('Y'); ?>
            </p>
        </div>
    </div>
</body>
</html>
