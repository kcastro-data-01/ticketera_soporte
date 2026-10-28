"""Copia los datos de la base SQLite actual a Postgres (Neon, para Vercel).

Uso (dentro del contenedor de Docker, donde está la base real):

    docker compose exec -e DESTINO_URL="postgres://…" ticketera python -m backend.copiar_a_postgres

* Origen: ``DATABASE_URL`` (en Docker, ``/data/ticketera.db``) o ``--origen``.
* Destino: ``DESTINO_URL`` (la cadena de Neon **sin** pooler). Se lee del
  entorno para que la contraseña no quede en el historial de comandos.
* Crea las tablas en el destino y copia todo conservando los ``id``
  (usuarios, tickets, comentarios, historial, correos procesados,
  explicaciones y la caché de tokens del buzón). Si el destino ya tiene datos
  no hace nada, salvo con ``--reemplazar`` (borra los del destino primero).
* Al final ajusta los contadores de ``id`` de Postgres y muestra cuántas filas
  hay en cada tabla del origen y del destino.

Conviene que nadie use la ticketera mientras se copia (y que el correo de
Docker esté apagado: ``CORREO_ACTIVO=0``).
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import delete, func, insert, select, text

from backend.database import Base, build_engine, es_sqlite, init_db, resolve_database_url
from backend.services.correo_auth import AlmacenBD, ruta_cache

LOTE = 500


def contar(conn, tabla) -> int:
    return conn.execute(select(func.count()).select_from(tabla)).scalar()


def tablas():
    """Las tablas de los modelos, padres antes que hijos (claves foráneas)."""
    from backend import models  # noqa: F401  (registra los modelos)

    return Base.metadata.sorted_tables


def ajustar_secuencias(conn) -> None:
    """Después de insertar con ``id`` fijo, el próximo ``id`` de Postgres
    tiene que seguir al mayor copiado."""
    for tabla in tablas():
        if "id" not in tabla.c:
            continue
        conn.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{tabla.name}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {tabla.name}), 0) + 1, false)"
        ))


def copiar(origen_url: str, destino_url: str, reemplazar: bool = False, imprimir=print,
           cache_archivo=None) -> int:
    origen = build_engine(resolve_database_url(origen_url))
    destino = build_engine(resolve_database_url(destino_url))
    if es_sqlite(destino):
        imprimir("DESTINO_URL tiene que ser una base Postgres (postgres://…).")
        return 1
    # El esquema del origen al día (migraciones de SQLite) y el destino creado.
    init_db(origen)
    init_db(destino)
    # La caché de tokens del archivo de antes, si todavía no estaba en la base.
    if cache_archivo is not None:
        from sqlalchemy.orm import sessionmaker

        AlmacenBD(sessionmaker(bind=origen), importar_de=cache_archivo).leer()

    with destino.connect() as conn:
        con_datos = [t.name for t in tablas() if contar(conn, t)]
    if con_datos and not reemplazar:
        imprimir(f"El destino ya tiene datos en {', '.join(con_datos)}. No se copió nada "
                 "(usa --reemplazar para borrarlos y copiar de nuevo).")
        return 1

    with origen.connect() as leer, destino.begin() as escribir:
        if con_datos:
            for tabla in reversed(tablas()):
                escribir.execute(delete(tabla))
        for tabla in tablas():
            filas = [dict(fila._mapping) for fila in leer.execute(select(tabla))]
            for inicio in range(0, len(filas), LOTE):
                escribir.execute(insert(tabla), filas[inicio:inicio + LOTE])
        ajustar_secuencias(escribir)

    errores = 0
    with origen.connect() as a, destino.connect() as b:
        imprimir(f"{'tabla':<22}{'origen':>8}{'destino':>9}")
        for tabla in tablas():
            n_origen, n_destino = contar(a, tabla), contar(b, tabla)
            marca = "" if n_origen == n_destino else "  ← distinto"
            errores += bool(marca)
            imprimir(f"{tabla.name:<22}{n_origen:>8}{n_destino:>9}{marca}")
    origen.dispose()
    destino.dispose()
    if errores:
        imprimir("La copia no coincide: revisa los mensajes de arriba.")
        return 1
    imprimir("Copia terminada.")
    return 0


def main(argv=None, env=None, imprimir=print) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description="Copia la base SQLite a Postgres (Neon).")
    parser.add_argument("--origen", help="URL o ruta de la base SQLite (por defecto DATABASE_URL)")
    parser.add_argument("--reemplazar", action="store_true",
                        help="borrar los datos del destino antes de copiar")
    args = parser.parse_args(argv)
    destino = (env.get("DESTINO_URL") or "").strip()
    if not destino:
        imprimir("Falta DESTINO_URL (la cadena de conexión de Neon, sin pooler).")
        return 1
    origen = args.origen or env.get("DATABASE_URL")
    if not es_sqlite(resolve_database_url(origen)):
        imprimir("El origen tiene que ser la base SQLite (DATABASE_URL o --origen).")
        return 1
    return copiar(origen, destino, args.reemplazar, imprimir,
                  cache_archivo=ruta_cache(env.get("CORREO_M365_CACHE")))


if __name__ == "__main__":
    sys.exit(main())
