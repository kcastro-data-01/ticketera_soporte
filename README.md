# Ticketera de Soporte

Sistema de gestión de tickets de soporte desarrollado como práctica de Pasantes de Inteligencia Artificial.

## Requisitos funcionales

- Crear un ticket con título y descripción.
- Seleccionar categoría y prioridad.
- Cambiar el estado entre **Nuevo**, **En proceso**, **Resuelto** y **Cerrado**.
- Asignar el ticket a una persona.
- Agregar comentarios al ticket.
- Ver listado de tickets.
- Buscar tickets.
- Filtrar tickets.
- Consultar el historial de cambios de cada ticket.

## Tecnologías

| Capa | Tecnología |
|------|------------|
| Backend | Python + FastAPI |
| Base de datos | SQLite |
| Frontend | HTML / CSS / JavaScript |
| Infraestructura | Docker |
| Control de versiones | Git / GitHub |

## Estructura del proyecto

```
ticketera_soporte/
├── docker-compose.yml
├── Dockerfile
├── .gitignore
├── requirements.txt
├── README.md
├── docs/
│   └── plan_desarrollo.md      # Plan de desarrollo por tareas
├── backend/
│   ├── main.py                 # Aplicación FastAPI
│   ├── database.py             # Conexión y sesiones de SQLite
│   ├── models.py               # Modelos de datos (SQLAlchemy)
│   ├── schemas.py              # Esquemas de validación (Pydantic)
│   ├── constants.py            # Estados, categorías y prioridades
│   ├── routers/                # Endpoints de la API
│   ├── services/               # Lógica de negocio y auditoría
│   └── tests/                  # Pruebas con pytest
└── frontend/
    ├── index.html
    ├── crear.html
    ├── detalle.html
    ├── css/
    └── js/
```

## Decisiones de diseño

1. **Categorías fijas:** Incidente, Consulta, Solicitud, Mantenimiento.
2. **Sin autenticación:** existen usuarios mínimos (solo para asignar tickets y firmar comentarios/historial).
3. **Idioma:** variables y funciones en inglés; textos visibles de la interfaz en español.

## Cómo ejecutar

_Instrucciones completas disponibles al finalizar las tareas de implementación._

### Instalación de dependencias

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> **Nota:** en sistemas Debian/Ubuntu con Python gestionado (PEP 668) el paquete
> `python3-venv` puede no estar disponible. En ese caso, crear el entorno sin pip
> interno e instalar con el pip del sistema apuntando al venv:
>
> ```bash
> python3 -m venv --without-pip .venv
> pip3 --python .venv/bin/python install -r requirements.txt
> ```

### Base de datos

SQLite crea el archivo `ticketera.db` en la raíz del proyecto la primera vez que
se llama a `init_db()` (se hará automáticamente al arrancar la API en la Tarea 3).
El archivo está excluido de Git (`.gitignore`) y sus tablas son: `users`,
`tickets`, `comments` y `history`.

### Pruebas

```bash
pytest backend/tests
```

## Plan de desarrollo

El desarrollo se realiza estrictamente por tareas. El plan completo está en
[docs/plan_desarrollo.md](docs/plan_desarrollo.md).
