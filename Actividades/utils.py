import time
import functools
import threading
from config import logger

# Global cache storage
_CACHE = {}
_CACHE_LOCK = threading.Lock()

def medir_tiempo(func):
    """Decorador para medir el tiempo de ejecución de una función y loguearlo."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        inicio = time.time()
        resultado = func(*args, **kwargs)
        fin = time.time()
        logger.info(f"[PERFORMANCE] {func.__name__} tardó {fin - inicio:.4f} segundos")
        return resultado
    return wrapper

def cache_decorator(func):
    """
    Decorador de caché simple (memoization) para funciones sin argumentos
    o con argumentos que puedan ser usados como llaves de diccionario.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Crear una llave basada en el nombre de la función y sus argumentos
        key = (func.__name__, args, frozenset(kwargs.items()))
        
        with _CACHE_LOCK:
            if key in _CACHE:
                return _CACHE[key]
        
        resultado = func(*args, **kwargs)
        
        with _CACHE_LOCK:
            _CACHE[key] = resultado
            
        return resultado
    return wrapper

def clear_cache():
    """Limpia el caché global."""
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = {}
    logger.info("Caché global limpiado.")
