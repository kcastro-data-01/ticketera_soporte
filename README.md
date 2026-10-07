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

### Arranque de la API

```bash
.venv/bin/uvicorn backend.main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000` y la documentación interactiva
en `http://127.0.0.1:8000/docs`.

### Health check

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

### Crear un ticket

```bash
curl -X POST http://127.0.0.1:8000/api/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "title": "No enciende la impresora",
    "description": "La impresora del piso 2 no responde desde ayer.",
    "category": "Incidente",
    "priority": "Alta"
  }'
```

Devuelve `201 Created` con el ticket creado (el estado inicial es `Nuevo`).
Categorías válidas: `Incidente`, `Consulta`, `Solicitud`, `Mantenimiento`.
Prioridades válidas: `Baja`, `Media`, `Alta`, `Crítica`. Los datos inválidos
responden `422 Unprocessable Entity`.

### Editar un ticket

```bash
curl -X PATCH http://127.0.0.1:8000/api/tickets/1 \
  -H "Content-Type: application/json" \
  -d '{"title": "Nuevo título del ticket"}'
```

Actualización **parcial**: envía solo los campos que quieras cambiar entre
`title`, `description`, `category` y `priority`. Respuestas: `200 OK` con el
ticket actualizado, `404 Not Found` si el ticket no existe y `422` si algún
campo es inválido o la petición no contiene campos modificables. Los campos
`id`, `state`, `assigned_to_id` y `created_at` no se pueden modificar con este
endpoint; `updated_at` se actualiza automáticamente.

### Listar tickets

```bash
curl http://127.0.0.1:8000/api/tickets
```

Devuelve `200 OK` con la lista de todos los tickets almacenados, ordenados de
más reciente a más antiguo. Cada elemento contiene `id`, `title`, `description`,
`category`, `priority`, `state`, `assigned_to_id`, `created_at` y
`updated_at`. Si no hay tickets, responde `[]`.

### Consultar un ticket

```bash
curl http://127.0.0.1:8000/api/tickets/1
```

Devuelve `200 OK` con el ticket solicitado (mismos campos que el listado) o
`404 Not Found` si el id no existe. La consulta no modifica el ticket.

### Base de datos

SQLite crea el archivo `ticketera.db` en la raíz del proyecto automáticamente
al arrancar la API (`init_db()` se ejecuta en el arranque).
El archivo está excluido de Git (`.gitignore`) y sus tablas son: `users`,
`tickets`, `comments` y `history`.

### Pruebas

```bash
pytest backend/tests
```

## Plan de desarrollo

El desarrollo se realiza estrictamente por tareas. El plan completo está en
[docs/plan_desarrollo.md](docs/plan_desarrollo.md).
