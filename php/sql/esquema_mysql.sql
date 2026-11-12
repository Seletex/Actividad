-- Esquema para MySQL (phpMyAdmin). La aplicación lo crea solo con instalar.php,
-- pero este archivo sirve para revisarlo o crearlo a mano.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS usuarios (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password_hash VARCHAR(128) DEFAULT NULL,
    password_salt VARCHAR(64) DEFAULT NULL,
    debe_cambiar_contrasena TINYINT(1) NOT NULL DEFAULT 0,
    revision_sesion INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS registros (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    usuario VARCHAR(50) DEFAULT NULL,
    tipo_actividad TEXT,
    fecha DATETIME DEFAULT NULL,
    dependencia VARCHAR(150) DEFAULT NULL,
    solicitante VARCHAR(150) DEFAULT NULL,
    tipo_solicitud VARCHAR(150) DEFAULT NULL,
    medio_solicitud VARCHAR(150) DEFAULT NULL,
    descripcion TEXT,
    cumplido VARCHAR(10) DEFAULT NULL,
    fecha_atencion VARCHAR(10) DEFAULT NULL,
    observaciones TEXT,
    sync_uid VARCHAR(64) DEFAULT NULL,
    updated_at VARCHAR(30) DEFAULT NULL,
    borrado TINYINT(1) NOT NULL DEFAULT 0,
    busqueda MEDIUMTEXT,
    KEY idx_registros_usuario (usuario),
    KEY idx_registros_fecha (fecha),
    KEY idx_registros_borrado (borrado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS listas_globales (
    tipo VARCHAR(40) NOT NULL,
    valor TEXT NOT NULL,
    KEY idx_lista_tipo (tipo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS actividades_personales (
    username VARCHAR(50) NOT NULL,
    actividad TEXT NOT NULL,
    KEY idx_personal_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS configuracion_usuario (
    username VARCHAR(50) NOT NULL,
    clave VARCHAR(60) NOT NULL,
    valor MEDIUMTEXT,
    PRIMARY KEY (username, clave)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bitacora (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    usuario VARCHAR(50) DEFAULT NULL,
    accion VARCHAR(60) DEFAULT NULL,
    detalle TEXT,
    ip VARCHAR(64) DEFAULT NULL,
    fecha VARCHAR(30) DEFAULT NULL,
    KEY idx_bitacora_fecha (fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sesiones (
    token VARCHAR(80) NOT NULL PRIMARY KEY,
    usuario VARCHAR(50) DEFAULT NULL,
    revision INT NOT NULL DEFAULT 0,
    creado VARCHAR(30) DEFAULT NULL,
    visto VARCHAR(30) DEFAULT NULL,
    ip VARCHAR(64) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS intentos_login (
    ip VARCHAR(64) NOT NULL PRIMARY KEY,
    fallos INT NOT NULL DEFAULT 0,
    ultimo INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tickets (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    radicado VARCHAR(30) NOT NULL UNIQUE,
    dependencia VARCHAR(150) NOT NULL,
    solicitante VARCHAR(150) NOT NULL,
    correo VARCHAR(150) DEFAULT NULL,
    telefono VARCHAR(50) DEFAULT NULL,
    tipo_solicitud VARCHAR(150) NOT NULL,
    prioridad VARCHAR(20) NOT NULL DEFAULT 'Media',
    descripcion TEXT NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
    tecnico_asignado VARCHAR(50) DEFAULT NULL,
    tecnicos_colaboradores TEXT,
    solucion TEXT,
    fecha_creacion DATETIME NOT NULL,
    fecha_atencion DATETIME DEFAULT NULL,
    fecha_cierre DATETIME DEFAULT NULL,
    actividades_ids VARCHAR(255) DEFAULT NULL,
    KEY idx_tickets_radicado (radicado),
    KEY idx_tickets_estado (estado),
    KEY idx_tickets_fecha (fecha_creacion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Historial de respaldos entre Render (Neon) y esta copia en MySQL.
CREATE TABLE IF NOT EXISTS sincronizacion (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL,
    iniciado VARCHAR(30) DEFAULT NULL,
    terminado VARCHAR(30) DEFAULT NULL,
    estado VARCHAR(20) DEFAULT NULL,
    detalle MEDIUMTEXT,
    KEY idx_sincronizacion_fecha (iniciado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
