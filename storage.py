"""Fail closed when durable storage is required but unavailable."""
import os
from pathlib import Path


def database_path(root):
    directory=Path(os.environ.get('LUMIGO_DATA_DIR',str(root)))
    path=Path(os.environ.get('LUMIGO_DB',str(directory/'lumigo.sqlite3')))
    return path


def validate_storage(path):
    if os.environ.get('LUMIGO_REQUIRE_PERSISTENT')=='1':
        mount=Path(os.environ.get('LUMIGO_DATA_DIR','/var/data')).resolve()
        if not os.path.ismount(mount) or not path.resolve().is_relative_to(mount):
            raise RuntimeError('No hay un disco persistente montado para la base de datos. Inicio cancelado para proteger los registros.')
        if not path.exists() and os.environ.get('LUMIGO_ALLOW_EMPTY_DB')!='1':
            raise RuntimeError('Falta la base de datos en el disco. Restaura el respaldo verificado antes de iniciar. No se creará una base vacía automáticamente.')
    path.parent.mkdir(parents=True,exist_ok=True)
