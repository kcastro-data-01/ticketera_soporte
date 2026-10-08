# Ticketera de Soporte

Sistema de gestión de tickets de soporte desarrollado como práctica de Pasantes de Inteligencia Artificial.

**Objetivo:** registrar, priorizar, asignar y dar seguimiento a solicitudes de
soporte mediante una API REST y una interfaz web sencilla: crear tickets con
categoría y prioridad, asignarlos a una persona, comentarlos, buscarlos y
filtrarlos, y consultar su historial de cambios.

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

> El estado real de cada requisito (implementado o pendiente) está en
> [Funcionalidades](#funcionalidades-implementadas-y-pendientes).

## Funcionalidades implementadas y pendientes

**Implementadas**

- API: health check, creación, consulta, listado, búsqueda y filtros de
  tickets, edición de datos básicos, asignación/desasignación, cambio de
  estado con máquina de estados (RF3), alta y listado de usuarios, creación
  de comentarios y lectura del historial de cambios.
- Frontend (servido por la misma aplicación): listado con búsqueda y filtros,
  creación de tickets, y pantalla de detalle con edición, asignación,
  cambio de estado, comentarios y consulta de historial.
- Ejecución local y con Docker (`docker compose up --build`), con persistencia
  de SQLite en un volumen.
- Suite de pruebas con pytest (151 pruebas), pruebas del frontend con
  `node:test` (10 pruebas) y documentación en
  [docs/api.md](docs/api.md).

**Pendientes**

- **Listado de comentarios** — solo existe la creación
  (`GET .../comments` no está implementado).
- **Registro de historial para el resto de acciones (RF9, escritura)** — la
  lectura existe y el cambio de estado ya deja su entrada, pero creación,
  edición, asignación y comentarios todavía no crean registros en `history`.
- **Paginación** — los listados devuelven el resultado completo.

**Fuera de alcance por decisión aprobada:** autenticación y autorización (la
API es abierta; los usuarios solo sirven para asignación y firma).

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
├── .dockerignore
├── .gitignore
├── pytest.ini                  # configuración de pytest
├── requirements.txt
├── README.md
├── docs/
│   ├── plan_desarrollo.md      # Plan de desarrollo por tareas
│   └── api.md                  # Documentación de la API
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
    ├── index.html              # Listado con búsqueda y filtros
    ├── crear.html              # Alta de tickets
    ├── detalle.html            # Detalle y gestión del ticket
    ├── css/
    ├── js/
    └── tests/                  # Pruebas del frontend (node:test)
```

## Decisiones de diseño

1. **Categorías fijas:** Incidente, Consulta, Solicitud, Mantenimiento.
2. **Sin autenticación:** existen usuarios mínimos (solo para asignar tickets y firmar comentarios/historial).
3. **Idioma:** variables y funciones en inglés; textos visibles de la interfaz en español.

## Requisitos

- **Ejecución local:** Python 3.10 o superior con `pip` (probado con Python
  3.12 y 3.14).
- **Ejecución con Docker:** Docker con el plugin de Docker Compose
  (`docker compose version` debe responder).
- **Git** para el control de versiones (opcional para ejecutar el proyecto).

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

### Ejecutar con Docker

**Requisitos:** Docker con el plugin de Docker Compose (`docker compose
version` debe responder).

Levantar la aplicación (API + frontend) con un solo comando:

```bash
docker compose up --build
```

Una vez iniciada, abre <http://localhost:8000> (frontend), la API en
<http://localhost:8000/docs> y comprueba el estado con:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Detener los servicios:

```bash
docker compose down      # detiene y borra el contenedor; los datos se conservan
docker compose down -v   # igual, pero borra también el volumen con la base de datos
```

**Persistencia de SQLite en Docker:** el contenedor no usa el `ticketera.db`
del proyecto (ese archivo sigue siendo la base de desarrollo local y no se
modifica). `docker-compose.yml` define la variable de entorno
`DATABASE_URL=sqlite:////data/ticketera.db` y monta el volumen nombrado
`ticketera-data` en `/data`, por lo que la base del contenedor sobrevive a
`docker compose down`, a `docker compose up --build` y a la recreación del
contenedor. Solo `docker compose down -v` (o borrar el volumen con
`docker volume rm`) elimina esos datos. En ejecución local, al no definir
`DATABASE_URL`, se usa el valor por defecto: `ticketera.db` en la raíz del
proyecto.

### Frontend

Con la API arrancada, abre <http://127.0.0.1:8000/> en el navegador. FastAPI
sirve los archivos de `frontend/` desde el mismo origen que la API (montaje
estático añadido al final de `backend/main.py`), por lo que no hace falta
CORS ni otro servidor: abrir el HTML con `file://` o con
`python -m http.server` bloquearía los `fetch` a la API por ser cross-origin.

La pantalla permite:

- ver el listado de tickets (ID, título, categoría, prioridad, estado,
  persona asignada y fecha de creación);
- buscar por título o descripción (usa el parámetro `search`);
- filtrar por categoría, prioridad y estado (parámetros `category`,
  `priority` y `state`), con opción "Todos/Todas" en cada selector;
- combinar búsqueda y filtros con **Buscar** (solo se envían los parámetros
  con valor) y volver al listado completo con **Limpiar filtros**.

Estados visibles: `Cargando...`, `No hay tickets para mostrar.` y
`Error al comunicarse con la API.`. El nombre de la persona asignada se
resuelve con `GET /api/users` (si no es posible, se muestra `Usuario #id`;
si el ticket no está asignado, `—`).

El botón **Nuevo ticket** de la cabecera abre `/crear.html`, un formulario
(título, descripción, categoría y prioridad) que da de alta tickets con
`POST /api/tickets`: valida en el navegador que título y descripción no
estén vacíos, muestra `Guardando...` mientras envía e impide envíos
duplicados, presenta el detalle de validación si la API responde `422`, un
mensaje de error si falla la red o el servidor, y al crearse el ticket
muestra la confirmación y redirige al listado.

El **ID** de cada fila del listado abre `/detalle.html?id={id}`, la pantalla
de detalle y gestión: muestra los 9 datos del ticket (ID, título, descripción,
categoría, prioridad, estado, persona asignada y fechas de creación y
actualización) con `GET /api/tickets/{id}` — si no existe se muestra un
mensaje claro — y permite, con los endpoints existentes:

- **editar** título, descripción, categoría y prioridad (`PATCH
  /api/tickets/{id}`): valida en el navegador los campos vacíos, presenta el
  detalle de validación si la API responde `422` y, tras un cambio exitoso,
  recarga el ticket para actualizar la información en pantalla;
- **asignar o desasignar** una persona: el selector se llena con
  `GET /api/users` e incluye la opción "Sin asignar" (`PATCH
  /api/tickets/{id}/assign`);
- **cambiar el estado** (`PATCH /api/tickets/{id}/state`): muestra el estado
  actual y solo ofrece los destinos posibles desde él — `Nuevo → En proceso →
  Resuelto → Cerrado` —, con confirmación si el cambio se aplica (`200`),
  mensaje del backend si la transición no está permitida (`409`) y una nota
  cuando el ticket está `Cerrado` (estado final, sin transiciones); el
  selector se desactiva en ese caso y el backend vuelve a validar siempre;
- **agregar comentarios** (`POST /api/tickets/{id}/comments`) con
  confirmación de creación; la consulta de los comentarios existentes queda
  pendiente de la tarea correspondiente, ya que el backend todavía no expone
  un endpoint para listarlos (se indica en la propia pantalla);
- **consultar el historial de cambios** con el botón **Ver historial**
  (`GET /api/tickets/{id}/history`): muestra una tabla con fecha y hora,
  persona (`—` si no hay), acción y detalle (`campo: anterior → nuevo`) en
  orden cronológico; maneja historial vacío (`No hay cambios registrados
  para este ticket.`), ticket inexistente (`404` del backend), error HTTP y
  fallo de red. Cada cambio de estado exitoso crea una entrada de historial
  (acción `Cambio de estado`) desde el backend, en la misma operación que la
  actualización del ticket; el resto de acciones (creación, edición,
  asignación, comentarios) todavía no deja registro, por lo que esas
  operaciones no aparecen en la tabla.

Todos los botones se deshabilitan mientras hay una operación en curso para
evitar envíos duplicados.

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

### Listar, buscar y filtrar tickets

```bash
# Todos los tickets (más recientes primero)
curl http://127.0.0.1:8000/api/tickets

# Búsqueda parcial + filtros combinados con AND
curl "http://127.0.0.1:8000/api/tickets?search=correo&priority=Alta&state=Nuevo"
```

Devuelve `200 OK` con la lista de los tickets almacenados, ordenados de más
reciente a más antiguo. Cada elemento contiene `id`, `title`, `description`,
`category`, `priority`, `state`, `assigned_to_id`, `created_at` y
`updated_at`. Si no hay tickets, responde `[]`.

Parámetros de consulta (todos opcionales y combinables entre sí):

| Parámetro | Valores | Efecto |
|-----------|---------|--------|
| `search` | texto libre | coincidencia parcial en `title` o `description`, sin distinguir mayúsculas; vacío o solo espacios equivale a no enviarlo; sin coincidencias → `200` con `[]` |
| `category` | `Incidente`, `Consulta`, `Solicitud`, `Mantenimiento` | filtra por categoría |
| `priority` | `Baja`, `Media`, `Alta`, `Crítica` | filtra por prioridad |
| `state` | `Nuevo`, `En proceso`, `Resuelto`, `Cerrado` | filtra por estado |

Sin parámetros el comportamiento es el original (listado completo). Un valor
fuera de los enums (`category`, `priority`, `state`) responde `422`. No hay
paginación ni ordenamiento configurable todavía.

### Consultar un ticket

```bash
curl http://127.0.0.1:8000/api/tickets/1
```

Devuelve `200 OK` con el ticket solicitado (mismos campos que el listado) o
`404 Not Found` si el id no existe. La consulta no modifica el ticket.

### Crear y listar usuarios

```bash
curl -X POST http://127.0.0.1:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Ana Pérez", "email": "ana@soporte.local", "role": "Soporte"}'

curl http://127.0.0.1:8000/api/users
```

`POST /api/users` devuelve `201` con `{id, name, email, role}`. Errores:
`422` si `name` está vacío, el `email` no tiene formato válido o el `role` no
es `Administrador`/`Soporte`; `409 Conflict` si el email ya está registrado.
`GET /api/users` devuelve `200` con la lista de usuarios (solo lectura).

### Asignar o desasignar un ticket

```bash
curl -X PATCH http://127.0.0.1:8000/api/tickets/1/assign \
  -H "Content-Type: application/json" \
  -d '{"assigned_to_id": 1}'

curl -X PATCH http://127.0.0.1:8000/api/tickets/1/assign \
  -H "Content-Type: application/json" \
  -d '{"assigned_to_id": null}'
```

Asigna un usuario existente al ticket (o lo desasigna con `null`). Respuestas:
`200` con el ticket actualizado, `404` si el ticket o el usuario no existen,
`422` si falta el campo. Solo cambian `assigned_to_id` y `updated_at`.

### Agregar comentarios a un ticket

```bash
curl -X POST http://127.0.0.1:8000/api/tickets/1/comments \
  -H "Content-Type: application/json" \
  -d '{"content": "Hola, ¿hay novedades?"}'
```

Crea un comentario sobre un ticket existente. Respuestas: `201` con
`{id, ticket_id, author, content, created_at}`, `404` si el ticket no existe
y `422` si `content` falta, está vacío, es solo espacios o supera los 2000
caracteres. `author` es opcional (por defecto `"Anónimo"`). Solo existe la
creación: el listado de comentarios no está implementado todavía.

### Consultar el historial de cambios

```bash
curl http://127.0.0.1:8000/api/tickets/1/history
```

Devuelve `200 OK` con las entradas de auditoría del ticket en la tabla
`history`, ordenadas de más antigua a más reciente (sin paginación). Cada
entrada contiene exactamente los campos del modelo: `id`, `ticket_id`,
`action`, `field`, `old_value`, `new_value`, `author` y `created_at`; los
opcionales vienen en `null` cuando el registro no los define. Respuestas:
`200` con `[]` si el ticket no tiene entradas y `404` si el ticket no existe.

> **Alcance actual:** el endpoint solo **lee** el historial. Hoy ninguna
> operación de la API crea entradas en `history` (el registro de auditoría
> está fuera del alcance de esta tarea), así que un ticket creado o editado
> por la API responderá `[]` hasta que ese registro se implemente.

### Base de datos

SQLite crea el archivo `ticketera.db` en la raíz del proyecto automáticamente
al arrancar la API (`init_db()` se ejecuta en el arranque).
El archivo está excluido de Git (`.gitignore`) y sus tablas son: `users`,
`tickets`, `comments` y `history`.

### Pruebas

```bash
.venv/bin/python -m pytest -q
# o, con pytest instalado en el entorno activo:
pytest

# Pruebas del frontend (Node.js, sin dependencias):
node --test frontend/tests/app_errors.test.js
```

La suite completa (151 pruebas) usa bases de datos temporales por test y no
modifica `ticketera.db`. Las 10 pruebas del frontend cargan
`frontend/js/app.js` en un contexto aislado y verifican el manejo de
errores de `fetchTickets()` (conexión, error HTTP, respuesta inválida y
casos de éxito), comprobando en cada caso que una ejecución realiza
exactamente una petición HTTP.

### Documentación de la API

El detalle de cada endpoint (método, parámetros, body, respuestas, errores y
ejemplos), junto con el mapeo RF1–RF9 y la lista de lo **no implementado**,
está en [docs/api.md](docs/api.md). La documentación interactiva se sirve en
`/docs` con la aplicación arrancada.

## Plan de desarrollo

El desarrollo se realiza estrictamente por tareas. El plan completo está en
[docs/plan_desarrollo.md](docs/plan_desarrollo.md).
