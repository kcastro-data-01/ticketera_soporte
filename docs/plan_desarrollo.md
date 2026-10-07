# Plan de desarrollo — Ticketera de Soporte

Plan aprobado el 2026-10-07. Desarrollo estrictamente por tareas: cada tarea se
implementa, se prueba, se documenta y se commitea antes de pasar a la siguiente.
**No se hace `push` a GitHub sin autorización.**

## Requisitos funcionales

| # | Requisito |
|---|-----------|
| RF1 | Crear ticket (título + descripción) |
| RF2 | Seleccionar categoría y prioridad |
| RF3 | Cambiar estado: Nuevo → En proceso → Resuelto → Cerrado |
| RF4 | Asignar ticket a una persona |
| RF5 | Agregar comentarios |
| RF6 | Listado de tickets |
| RF7 | Buscar tickets |
| RF8 | Filtrar tickets |
| RF9 | Historial de cambios |

## Decisiones de diseño aprobadas

1. **Categorías fijas:** Incidente, Consulta, Solicitud, Mantenimiento.
2. **Sin autenticación.** Usuarios mínimos (tabla `users`) solo para asignar
   tickets y como autor de comentarios/historial.
3. **Idioma:** variables y funciones en inglés; textos visibles de la interfaz
   en español. En consecuencia, tablas, columnas y campos de la API usan
   identificadores en inglés, mientras que los valores de los enums
   (`Nuevo`, `Incidente`, `Baja`…) se guardan en español porque se muestran
   directamente en la UI.
4. **Auditoría automática:** el historial se registra desde la capa de servicio,
   nunca desde el frontend.
5. **Estados, categorías y prioridades** como `enum` en código + columna de
   texto en SQLite.
6. **Transiciones de estado válidas:**
   - `Nuevo → En proceso`
   - `En proceso → Nuevo`, `En proceso → Resuelto`
   - `Resuelto → En proceso`, `Resuelto → Cerrado`
   - `Cerrado` es estado terminal.
   - Transición inválida → HTTP 409.
7. **Frontend estático** servido por el propio FastAPI (un solo contenedor Docker).
8. **Pruebas con pytest** sobre la API usando base de datos temporal.
9. **Base de datos:** archivo `ticketera.db` en la raíz del proyecto, creado
   automáticamente por `init_db()` y excluido de Git por `.gitignore`.

## Arquitectura

```
ticketera_soporte/
├── docker-compose.yml
├── Dockerfile
├── .dockerignore
├── .gitignore
├── requirements.txt
├── README.md
├── pytest.ini                    # configuración de pytest
├── ticketera.db                  # base de datos generada (ignorada por Git)
├── docs/
│   ├── plan_desarrollo.md        # este documento
│   └── api.md                    # documentación de endpoints
├── backend/
│   ├── main.py                   # app FastAPI + estáticos
│   ├── database.py               # engine, sesión, creación de tablas
│   ├── models.py                 # modelos SQLAlchemy
│   ├── schemas.py                # esquemas Pydantic
│   ├── constants.py              # enums: estados, prioridades, categorías
│   ├── routers/
│   │   ├── tickets.py
│   │   ├── users.py
│   │   ├── comentarios.py
│   │   └── catalogos.py
│   ├── services/
│   │   ├── ticket_service.py     # lógica + transiciones de estado
│   │   ├── user_service.py       # creación y consulta de usuarios
│   │   └── historial_service.py  # registro de auditoría
│   └── tests/
│       ├── conftest.py
│       ├── test_models.py
│       ├── test_constants.py
│       ├── test_smoke.py
│       ├── test_tickets.py
│       ├── test_users.py
│       ├── test_estados.py
│       ├── test_historial.py
│       ├── test_asignacion.py
│       ├── test_comentarios.py
│       └── test_busqueda_filtro.py
└── frontend/
    ├── index.html                # listado + búsqueda/filtros
    ├── detalle.html              # detalle, comentarios, historial
    ├── crear.html                # formulario de creación
    ├── css/estilos.css
    └── js/
        ├── app.js
        ├── detalle.js
        └── crear.js
```

### Modelo de datos

_Implementado en `backend/models.py`. Identificadores (tablas, columnas,
relaciones) en inglés según la decisión de idioma; los valores guardados en
`category`, `priority` y `state` son los textos en español de
`backend/constants.py` porque se muestran en la interfaz._

```
users    (id, name, email UNIQUE, role, is_active)
tickets  (id, title, description, category, priority, state,
          assigned_to_id -> users.id NULL,
          created_at, updated_at)
comments (id, ticket_id -> tickets.id CASCADE, author, content, created_at)
history  (id, ticket_id -> tickets.id CASCADE, action, field,
          old_value, new_value, author, created_at)
```

Restricciones a nivel de base de datos:
- `title`: entre 3 y 200 caracteres y no vacío.
- `description`, `content`, `action`: no vacíos.
- `category`, `priority`, `state`: valores de los enums aprobados.
- `email` de usuario: único.
- Claves foráneas activas (`PRAGMA foreign_keys=ON`).
- `state` inicial por defecto: `Nuevo`; `assigned_to_id` admite `NULL`.

### Endpoints

_Identificadores en inglés (decisión de idioma aprobada); los valores de
`state`, `category` y `priority` se envían en español tal como los muestra la
interfaz._

```
GET    /api/tickets                 ?search=&state=&category=&priority=&assigned_to=&page=&size=
POST   /api/tickets
GET    /api/tickets/{id}
PUT    /api/tickets/{id}            (title, description, category, priority)
PATCH  /api/tickets/{id}/state      {state, reason?}
PATCH  /api/tickets/{id}/assign     {user_id}
POST   /api/tickets/{id}/comments
GET    /api/tickets/{id}/comments
GET    /api/tickets/{id}/history
POST   /api/users
GET    /api/users
GET    /api/catalogs                (states, categories, priorities)
```

## Tareas

### Tarea 1 — Inicialización del proyecto
- **Objetivo:** esqueleto del repo, dependencias, Git listo.
- **Archivos:** `.gitignore`, `requirements.txt`, `README.md`,
  `docs/plan_desarrollo.md`, estructura de carpetas.
- **Prueba:** `pip install -r requirements.txt` sin errores;
  `python -c "import fastapi"` OK.
- **Criterio de terminado:** el entorno instala limpio, el plan está en `docs/`
  y existe un commit inicial.

### Tarea 2 — Base de datos y modelos
- **Objetivo:** capa de persistencia y modelos de datos.
- **Archivos:** `backend/database.py`, `backend/models.py`,
  `backend/constants.py`, `backend/tests/conftest.py`,
  `backend/tests/test_models.py`, `backend/tests/test_constants.py`,
  `pytest.ini`.
- **Prueba:** `pytest` verificando creación de tablas e inserción/lectura de un
  ticket de prueba.
- **Criterio de terminado:** `pytest` verde y la DB se genera al arrancar.

### Tarea 3 — Health check de la API
- **Objetivo:** aplicación FastAPI arrancable con un endpoint de salud que
  confirma que el servicio funciona.
- **Archivos:** `backend/main.py` (app + `lifespan` que ejecuta `init_db()`)
  y `backend/tests/test_smoke.py`; `README.md` (arranque y health check).
- **Prueba:** `pytest` — `GET /health` responde 200 con `{"status": "ok"}` y
  `GET /openapi.json` publica la ruta; `uvicorn backend.main:app` arranca;
  `GET /docs` accesible.
- **Criterio de terminado:** la app arranca con uvicorn, el health check
  responde y `pytest` está en verde.
- **Nota:** la redacción original de esta tarea incluía `backend/schemas.py`
  (esquemas Pydantic) y `backend/routers/catalogos.py` (endpoint de catálogo);
  no se implementaron en esta tarea y quedan pendientes de definirse en una
  tarea posterior.

### Tarea 4 — Crear ticket (RF1, RF2)
- **Objetivo:** alta de tickets mediante la API, con validación de entrada.
- **Archivos:** `backend/schemas.py` (`TicketCreate`, `TicketResponse`),
  `backend/routers/tickets.py`, `backend/services/ticket_service.py`,
  `backend/main.py` (registro del router),
  `backend/tests/conftest.py` (fixture `client`),
  `backend/tests/test_tickets.py`, `README.md` (ejemplo del endpoint).
- **Endpoint:** `POST /api/tickets` → `201` con el ticket creado
  (`id`, `title`, `description`, `category`, `priority`, `state`,
  `assigned_to_id`, `created_at`, `updated_at`).
- **Validaciones (422):** `title` obligatorio y con 3–200 caracteres (espejo
  del CHECK de la BD, con `strip`), `description` obligatoria y no vacía,
  `category` y `priority` deben ser valores de los enums de
  `backend/constants.py`.
- **Estado inicial:** el valor por defecto del modelo
  (`TicketState.NEW.value` = `Nuevo`), sin definirlo en el endpoint.
- **Prueba:** `pytest` — 15 pruebas: creación 201, datos reflejados,
  persistencia real en SQLite (sesión nueva), estado inicial según constants,
  presencia en `/openapi.json`, ausencia de título/descripción, título
  inválido, descripción en blanco, categoría y prioridad inválidas, nada
  persiste en payload inválido y guardado con `title` recortado.
- **Criterio de terminado:** la suite completa está en verde con la creación
  funcionando de extremo a extremo.
- **Nota:** la consulta individual `GET /api/tickets/{id}` de la redacción
  original no se implementó en esta tarea (solo creación); se implementó
  posteriormente en la **Tarea 7**.

### Tarea 5 — Consultar y listar tickets (RF6)
- **Objetivo:** devolver los tickets existentes mediante la API (solo lectura).
- **Archivos:** `backend/routers/tickets.py` (`GET`), 
  `backend/services/ticket_service.py` (`list_tickets`),
  `backend/tests/test_tickets.py` (sección de listado), `README.md`.
- **Endpoint:** `GET /api/tickets` → `200` con la lista de tickets
  (`list[TicketResponse]`), ordenada por `created_at` DESC e `id` DESC
  (más recientes primero). Reutiliza `TicketResponse`: sin nuevos schemas.
  Los parámetros de consulta (`q`, `state`, `category`, …) se ignoran hasta la
  Tarea 10.
- **Prueba:** `pytest` — 6 pruebas: lista vacía responde `200` y `[]`, los
  tickets creados aparecen en la lista, los datos corresponden a los registros
  almacenados (lectura con sesión nueva sobre SQLite), estructura de la
  respuesta (9 campos), presencia en `/openapi.json` y verificación de que la
  consulta no modifica los datos.
- **Criterio de terminado:** la suite completa está en verde con el listado
  funcionando.
- **Nota:** la redacción anterior de la Tarea 5 (historial de cambios, RF9) se
  retiró del plan para este alcance; RF9 queda pendiente de definirse en una
  tarea posterior.

### Tarea 6 — Editar ticket
- **Objetivo:** actualización parcial de los datos básicos de un ticket.
- **Archivos:** `backend/schemas.py` (`TicketUpdate` + validaciones
  compartidas `_validate_title`/`_validate_description`),
  `backend/services/ticket_service.py` (`update_ticket`),
  `backend/routers/tickets.py` (`PATCH`),
  `backend/tests/test_tickets.py` (sección de edición), `README.md`.
- **Endpoint:** `PATCH /api/tickets/{ticket_id}` → `200` con
  `TicketResponse`; `404` si el ticket no existe; `422` si algún campo es
  inválido o la petición no incluye ningún campo modificable.
- **Reglas:** campos opcionales `title`, `description`, `category`,
  `priority` (actualización parcial) con las mismas validaciones que la
  creación; `id`, `state`, `assigned_to_id` y `created_at` no son editables
  mediante este endpoint; `updated_at` se refresca automáticamente por el
  `onupdate=utc_now` del modelo (sin modificar `models.py`).
- **Prueba:** `pytest` — 17 pruebas: 200, edición individual de cada campo,
  campos combinados, persistencia en SQLite, 404 inexistente, 422 por título/
  descripción/categoría/prioridad inválidos, 422 sin campos modificables
  (`{}` y `title: null`), campos protegidos intactos (y 422 si solo se envían
  esos), `updated_at` incrementado y `created_at` intacto.
- **Criterio de terminado:** la suite completa está en verde.
- **Nota:** la redacción original incluía registrar la edición en el
  historial; **no se implementó** (RF9 sigue pendiente de definir).

### Tarea 7 — Consultar un ticket individual
- **Objetivo:** devolver un ticket existente por su id (solo lectura).
- **Archivos:** `backend/services/ticket_service.py` (`get_ticket`),
  `backend/routers/tickets.py` (`GET`), `backend/tests/test_tickets.py`
  (sección de consulta), `README.md`.
- **Endpoint:** `GET /api/tickets/{ticket_id}` → `200` con `TicketResponse`
  (mismo esquema del listado); `404` si el ticket no existe.
- **Reglas:** la consulta no modifica ningún dato del ticket.
- **Prueba:** `pytest` — 6 pruebas: ticket existente responde `200`, los datos
  coinciden con los almacenados (sesión nueva sobre SQLite), id inexistente →
  `404`, la consulta no modifica el ticket (instantánea antes/después),
  estructura de la respuesta (9 campos) y presencia en `/openapi.json`.
- **Criterio de terminado:** la suite completa está en verde.
- **Nota:** la máquina de estados (RF3) no forma parte de esta tarea; queda
  pendiente como **Tarea 18** de este plan.

### Tarea 8 — Usuarios y asignación (RF4)
- **Objetivo:** crear y listar usuarios mínimos; asignar/desasignar tickets.
- **Archivos:** `backend/schemas.py` (`UserCreate`, `UserResponse`,
  `TicketAssignment`), `backend/services/user_service.py`,
  `backend/services/ticket_service.py` (`assign_ticket` y excepciones
  `TicketNotFoundError`/`UserNotFoundError`), `backend/routers/users.py`,
  `backend/routers/tickets.py` (`PATCH …/assign`), `backend/main.py`
  (registro del router de usuarios), `backend/tests/test_users.py`,
  `backend/tests/test_asignacion.py`, `README.md`.
- **Endpoints nuevos:**
  - `POST /api/users` → `201` con `{id, name, email, role}`; `422` si `name`
    está vacío, `email` con formato inválido o `role` fuera de `UserRole`;
    `409 Conflict` si el email ya existe (sin crear duplicados).
  - `GET /api/users` → `200` con la lista de usuarios (solo lectura).
  - `PATCH /api/tickets/{ticket_id}/assign` con `{assigned_to_id}` → `200`
    con `TicketResponse`; `assigned_to_id: null` desasigna; `404` si el ticket
    o el usuario no existen; `422` si el campo falta.
- **Reglas:** no se alteran `title`, `description`, `category`, `priority`,
  `state` ni `created_at`; `updated_at` se refresca por el `onupdate` del
  modelo; todo se persiste en SQLite. Validación de email con regex propia
  (sin añadir dependencias).
- **Prueba:** `pytest` — 25 pruebas nuevas (13 de usuarios y 12 de
  asignación): creación 201 con datos reflejados, `name` vacío → 422, email
  inválido → 422, role inválido → 422, email duplicado → 409 sin segundo
  registro, listado 200 con estructura `{id, name, email, role}`, asignación
  200 con `assigned_to_id` almacenado y persistido, 404 por usuario/ticket
  inexistente, `null` desasigna y persiste, demás campos intactos,
  `updated_at` incrementado, estructura de `TicketResponse` y endpoints en
  OpenAPI.
- **Criterio de terminado:** la suite completa está en verde.
- **Nota:** la redacción original incluía auditar la asignación en el
  historial; **no se implementó** (RF9 sigue pendiente). La máquina de estados
  (RF3) permanece pendiente como **Tarea 18**.

### Tarea 9 — Comentarios (RF5)
- **Objetivo:** agregar un comentario a un ticket existente (creación únicamente).
- **Archivos:** `backend/schemas.py` (`CommentCreate`, `CommentResponse`,
  `COMMENT_MAX_LENGTH`), `backend/services/ticket_service.py`
  (`create_comment`, reutiliza `TicketNotFoundError`),
  `backend/routers/comentarios.py`, `backend/main.py` (registro del router),
  `backend/tests/test_comentarios.py`, `README.md`.
- **Endpoint nuevo:**
  - `POST /api/tickets/{ticket_id}/comments` → `201` con
    `{id, ticket_id, author, content, created_at}`; `404` si el ticket no
    existe; `422` si `content` falta, está vacío, es solo espacios o supera
    los 2000 caracteres (o si `author` se envía vacío).
- **Reglas:** `content` viene del cuerpo y `ticket_id` de la URL; el
  comentario se relaciona con el ticket mediante la relación existente
  `Comment.ticket`/`Ticket.comments` (**sin cambios de modelo ni BD**) y se
  persiste en SQLite. `author` es opcional (no hay autenticación) y por
  defecto queda `"Anónimo"`; el límite de 2000 caracteres se valida en la
  capa de API, no en la BD.
- **Prueba:** `pytest` — 13 pruebas nuevas: creación 201 con datos
  reflejados, autor por defecto y autor explícito, comentario asociado al
  ticket correcto, persistencia en SQLite y relación `ticket.comments`,
  ticket inexistente → 404, contenido vacío/solo espacios/sin campo → 422,
  contenido > 2000 caracteres → 422, autor vacío → 422, estructura de la
  respuesta y endpoint en OpenAPI.
- **Criterio de terminado:** la suite completa está en verde.
- **Nota:** la redacción original incluía listar comentarios en orden
  cronológico y que "el historial los mencione"; **no se implementó**
  (listado/edición/borrado de comentarios y RF9 de historial siguen
  pendientes). La máquina de estados (RF3) permanece pendiente como
  **Tarea 18**.

### Tarea 10 — Búsqueda y filtros de tickets (RF7, RF8)
- **Objetivo:** convertir `GET /api/tickets` en el endpoint central de
  consulta, sin crear endpoints nuevos ni cambiar su comportamiento por
  defecto.
- **Archivos:** `backend/routers/tickets.py` (query params con descripciones
  en español), `backend/services/ticket_service.py` (`list_tickets` con
  criterios y `_like_pattern`), `backend/tests/test_busqueda_filtro.py`,
  `README.md`.
- **Parámetros implementados (opcionales, combinables con AND):**
  - `search` → coincidencia **parcial** en `title` o `description` **sin
    distinguir mayúsculas** (SQL `ilike`); el texto se trata literalmente
    (se escapan `%` y `_`); vacío o solo espacios equivale a no enviarlo;
    sin coincidencias → `200` con `[]`.
  - `category` (`TicketCategory`), `priority` (`TicketPriority`) y `state`
    (`TicketState`) → únicamente valores existentes; un valor fuera del enum
    → `422` (validación nativa de FastAPI/Pydantic sobre el query param).
- **Reglas:** sin parámetros la consulta es idéntica a la anterior; orden
  `created_at DESC, id DESC` conservado; respuesta `list[TicketResponse]`
  sin cambios; consulta solo lectura; **cero cambios de modelo o BD** y
  ningún schema nuevo (los parámetros se declaran en el router).
- **Prueba:** `pytest` — 17 pruebas nuevas en `test_busqueda_filtro.py`:
  listado sin parámetros intacto, búsqueda por `title`, por `description`,
  case-insensitive (minúsculas y mayúsculas), sin resultados → `200 []`,
  `search` en blanco = sin parámetro, comodines `%`/`_` escapados, filtros
  aislados (`category`, `priority`, `state`), combinación de dos filtros,
  combinación `search` + filtros (incluye el ejemplo del enunciado
  `search=correo&priority=Alta&state=Nuevo`), `422` por valor inválido de
  cada enum, orden de más reciente a más antiguo con y sin filtros, y
  comprobación de que las consultas no modifican los tickets.
- **Criterio de terminado:** la suite completa está en verde (todos los
  escenarios de filtrado probados).
- **Nota:** la redacción original incluía paginación sin repetidos ni
  huecos; **no se implementó** (el `page`/`size` y el filtro `assigned_to`
  del API objetivo siguen pendientes y no están asignados a una tarea). El
  estado de las muestras de test se prepara directamente en la BD porque la
  máquina de estados (RF3) sigue pendiente como **Tarea 18**.

### Tarea 11 — Frontend: listado con búsqueda y filtros
- **Objetivo:** primera pantalla funcional que consulta la API.
- **Archivos:** `frontend/index.html`, `frontend/css/estilos.css`,
  `frontend/js/app.js` (JavaScript vanilla, sin frameworks ni librerías) y
  `backend/main.py` (montaje estático mínimo). Se eliminaron los `.gitkeep`
  de `frontend/css/` y `frontend/js/`.
- **Integración con FastAPI:** el frontend se sirve desde la propia API con
  `app.mount("/", StaticFiles(directory=..., html=True))` añadido **al final**
  de `main.py`, después de todas las rutas, para no eclipsar ningún endpoint
  existente (`/health` y `/api/*` siguen respondiendo igual). Era necesario:
  abrir el HTML con `file://` o con `python -m http.server` haría los
  `fetch` cross-origin y la API no envía cabeceras CORS; añadir
  `CORSMiddleware` habría sido un cambio backend mayor. Si en el futuro se
  prefiere no montar en `/`, la alternativa sería servirlo desde otro origen
  **con** CORS habilitado.
- **Funcionalidad:** listado vía `GET /api/tickets` con columnas ID,
  título, categoría, prioridad, estado, asignado a y fecha de creación; el
  nombre de la persona asignada se resuelve con `GET /api/users` (si no es
  posible → `Usuario #id`; sin asignar → `—`); búsqueda y filtros se envían
  **contra la API** con los parámetros ya existentes (`search`, `category`,
  `priority`, `state`), omitiendo los que no tienen valor; botones
  **Buscar** y **Limpiar filtros**; estados de interfaz `Cargando...`,
  `No hay tickets para mostrar.` y `Error al comunicarse con la API.`.
- **No implementado (por alcance):** creación, edición, asignación,
  comentarios, cambio de estado, historial, autenticación, paginación,
  Docker ni frameworks frontend.
- **Prueba:** `pytest -q` → **125 en verde** (sin regresiones; el montaje no
  afecta a las pruebas existentes) + validación manual: servidor real con
  uvicorn — `/` carga (200, 7 columnas, campos y botones presentes),
  `/css/estilos.css` y `/js/app.js` (200), `/health` intacto, búsqueda por
  título, por descripción, case-insensitive, filtros aislados, combinaciones
  (incluido `search=correo&priority=Alta&state=Nuevo`), resultado vacío
  (`200 []`), error de API (`422`), `state=En+proceso` decodificado y 404
  JSON en rutas definidas; además, un harness desechable de `node` sobre
  `app.js` con stubs de DOM/fetch verificó la construcción de URLs y los
  tres estados de interfaz (**20 comprobaciones, todas en verde**).
- **Criterio de terminado:** se puede buscar y filtrar desde la UI.

### Tarea 12 — Frontend: crear ticket
- **Objetivo:** alta de tickets desde la interfaz, reutilizando
  `POST /api/tickets` (sin endpoints nuevos).
- **Archivos:** `frontend/crear.html` (formulario), `frontend/js/crear.js`
  (JavaScript vanilla), `frontend/css/estilos.css` (reutilizado + clases
  mínimas nuevas: `.formulario`, `.enlace-boton`, `.estado.exito`,
  `button:disabled`, `textarea`) y `frontend/index.html` (enlace **Nuevo
  ticket** en la cabecera).
- **Formulario:** título, descripción, categoría y prioridad; los selects
  usan exactamente las opciones del backend (`Incidente`, `Consulta`,
  `Solicitud`, `Mantenimiento` / `Baja`, `Media`, `Alta`, `Crítica`) sin
  opción vacía, de modo que siempre hay valor válido.
- **Comportamiento:** validación en el navegador (`novalidate` + chequeo
  con `trim`: vacíos o solo espacios → mensaje en español sin llamar a la
  API); envío con `fetch` `POST /api/tickets` y `Content-Type:
  application/json`; estado `Guardando...` con botón deshabilitado y flag
  `enviando` que **impide envíos duplicados** (tras el éxito sigue bloqueado
  hasta redirigir); éxito → confirmación `Ticket #N creado correctamente`
  y redirección a `index.html` a los 1,5 s; `422` → detalle de validación
  de FastAPI en mensaje legible (`loc` + `msg`); error de red → `Error al
  comunicarse con la API.`; otro código no-OK → `HTTP nnn`.
- **No implementado (por alcance):** edición, asignación, comentarios,
  cambio de estado, historial, paginación, frameworks ni backend nuevo.
- **Prueba:** `pytest -q` → **125 en verde** (sin regresiones) +
  validación manual con servidor real: `/crear.html` (200, campos
  `form-crear`/`title`/`description`/`category`/`priority`/`guardar` y las
  8 opciones de enum), enlace `Nuevo ticket` en `/`, assets `200`,
  creación con el payload del formulario → `201` con el ticket creado,
  título de 2 caracteres → `422` con mensaje en español (mostrado por la
  UI), listado `GET /api/tickets` y `/health` intactos; además un harness
  desechable de `node` sobre `crear.js` (**26 comprobaciones, todas en
  verde**) cubrió recorte de espacios, los 3 mensajes de validación vacía,
  bloqueo sin llamar a la API, `Guardando...`, botón deshabilitado,
  anti-duplicados, payload exacto, interpretación del `422`, fallo de red,
  error `500`, confirmación con id, bloqueo post-éxito y redirección.
- **Criterio de terminado:** el alta funciona desde la UI y los errores se
  muestran.

### Tarea 13 — Frontend: detalle, edición, asignación y comentarios
- **Objetivo:** consultar y gestionar un ticket desde la UI con los endpoints
  existentes: ver los 9 datos del ticket (`GET /api/tickets/{id}`), editar
  título/descripción/categoría/prioridad (`PATCH /api/tickets/{id}`),
  asignar/desasignar (`GET /api/users` + `PATCH /api/tickets/{id}/assign`) y
  agregar comentarios (`POST /api/tickets/{id}/comments`). El ID de cada fila
  del listado abre `detalle.html?id={id}`.
- **Fuera de alcance (a propósito):** cambio de estado (Tarea 18) e historial
  (Tarea 14). La consulta de comentarios existentes queda **pendiente**: el
  backend solo expone `POST`, no `GET`, por lo que la pantalla permite
  agregar comentarios y muestra una nota explícita al respecto.
- **Archivos:** creados `frontend/detalle.html`, `frontend/js/detalle.js`;
  modificados `frontend/js/app.js` (enlace del ID), `frontend/css/estilos.css`
  (estilos de detalle y enlace de tabla).
- **Prueba:** manual — `pytest` 125 en verde; con el servidor real: apertura
  de ticket existente e inexistente (`404` con mensaje claro), edición con
  recarga de datos en pantalla (`updated_at` cambia), título de 2 caracteres y
  categoría inválida → `422` mostrado, alta de usuario (`role` obligatorio,
  enum `Administrador`/`Soporte`), asignación → `assigned_to_id: 1`,
  desasignación → `null`, usuario inexistente → `404`, comentario → `201`,
  listado y `/health` intactos; además un harness desechable de `node` sobre
  `detalle.js` y el enlace de `app.js` (**34 comprobaciones, todas en verde**)
  cubrió parseo del id por query string, render de los 9 campos, 404, payload
  del PATCH, validación local y `422`, recarga silenciosa post-éxito,
  bloqueo de botones y anti-duplicados, asignar/desasignar con `null`,
  mensajes del backend, alta y validación de comentarios y el enlace del
  listado.
- **Criterio de terminado:** todos los flujos de gestión (sin estados ni
  historial) funcionan desde la UI.

### Tarea 14 — Frontend: historial de cambios
- **Objetivo:** consultar desde la UI el historial de cambios de un ticket
  (RF9, solo lectura), con una forma clara de abrirlo desde `detalle.html`.
- **Endpoint:** `GET /api/tickets/{ticket_id}/history` — ya estaba previsto
  en la superficie de API del plan y era la única pieza que faltaba: el modelo
  `History` existía (`action`, `field`, `old_value`, `new_value`, `author`,
  `created_at`) pero no había forma de leerlo. Implementado como endpoint
  mínimo (esquema `HistoryResponse` espejo del modelo, servicio
  `get_ticket_history` y ruta en `routers/tickets.py`): `200` con las
  entradas ordenadas de más antigua a más reciente (`created_at` con `id`
  como desempate, sin paginación), `[]` si no hay entradas y `404 Ticket N
  no encontrado`. Solo lee: **no crea registros** ni modifica modelos/BD.
- **Alcance del historial consultable hoy (documentado, no es otra tarea):**
  ninguna operación de la API escribe en `history` — solo los tests de modelo
  insertan filas —, así que un ticket dado de alta o editado por la API
  responde `[]` y la UI muestra el estado vacío hasta que exista el registro
  de auditoría.
- **Frontend:** sección **Historial de cambios** en `detalle.html` con botón
  **Ver historial** que llama al endpoint y pinta una tabla `.listado` (Fecha
  y hora / Persona / Acción / Detalle) usando solo `textContent`; `Persona`
  muestra `—` sin autor y `Detalle` compone `campo: anterior → nuevo` con los
  campos reales (`—` si no hay). Estados manejados: `Cargando...`, vacío
  (`.estado.vacio`), `404` con el detalle del backend, `HTTP nnn` y fallo de
  red. El botón entra en la misma flag `ocupado` (4 botones bloqueados
  durante cualquier operación, anti-duplicados incluido).
- **Archivos:** creados `backend/tests/test_historial.py`; modificados
  `backend/schemas.py`, `backend/services/ticket_service.py`,
  `backend/routers/tickets.py`, `frontend/detalle.html`,
  `frontend/js/detalle.js`, `README.md`, `docs/plan_desarrollo.md`
  (`frontend/css/estilos.css` reutilizado sin cambios: `.listado` y
  `.estado.vacio` ya existían).
- **Prueba:** `pytest -q` → **131 en verde** (125 previos + 6 nuevos:
  `[]` sin entradas, `404`, orden cronológico, campos del modelo con opcionales
  en `null`, detalle del cambio y aislamiento entre tickets); harness
  desechable de `node` sobre `detalle.js` y el HTML (**27 comprobaciones, en
  verde**) cubrió presencia de la sección, ausencia de `innerHTML`, listener
  del botón, render de registros (fecha, `—`, acción y detalle), vacío, `404`,
  `500`, fallo de red, bloqueo/anti-duplicados y `formatDetalleHistorial`;
  manual con servidor real: ticket con historial (3 entradas insertadas
  directamente en la BD → `200` en orden), sin historial (`200 []`),
  inexistente (`404`), ruta visible en `openapi.json`, `detalle.html`/`detalle.js`
  `200` con el botón presente, `/health` y listado intactos.
- **Criterio de terminado:** el historial se consulta desde la UI, se ve
  legible y los errores/vacíos se muestran.

### Tarea 15 — Docker
- **Objetivo:** el sistema corre con un solo comando.
- **Archivos:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`,
  `README.md`.
- **Prueba:** `docker compose up --build` y flujo completo desde el navegador;
  persistencia de la DB tras reiniciar.
- **Criterio de terminado:** el contenedor levanta, sirve API + frontend y la
  DB persiste.

### Tarea 16 — Documentación final y revisión
- **Objetivo:** README completo y cierre.
- **Archivos:** `README.md`, `docs/plan_desarrollo.md`, `docs/api.md`.
- **Prueba:** RF1–RF9 mapeados a endpoints y pruebas; `pytest` completo en verde.
- **Criterio de terminado:** documentación cubre todo y `pytest` en verde.

### Tarea 17 — Push a GitHub (con autorización)
- **Objetivo:** publicar en GitHub.
- **Archivos:** ninguno nuevo.
- **Prueba:** `git log` y `git status` limpios.
- **Criterio de terminado:** push realizado con autorización expresa.

### Tarea 18 — Máquina de estados (RF3)
- **Objetivo:** permitir cambiar el estado de un ticket respetando las
  transiciones aprobadas (decisión 6).
- **Archivos:** `backend/services/ticket_service.py`,
  `backend/routers/tickets.py` (`PATCH /api/tickets/{id}/state`),
  `backend/tests/test_estados.py`.
- **Endpoint:** `PATCH /api/tickets/{id}/state` con `{state, reason?}`;
  transición inválida → HTTP 409; `Cerrado` es estado terminal.
- **Prueba:** `pytest` — transición válida OK; `Nuevo → Cerrado` → 409;
  `Cerrado` terminal.
- **Criterio de terminado:** todas las transiciones cubiertas por pruebas.
- **Estado:** ⬜ Pendiente de implementar. Registrada aquí para no entrar en
  conflicto con la **Tarea 7** (Consultar un ticket individual). El registro de
  estos cambios en el historial (RF9) se definirá en una tarea propia.

## Estado del avance

| Tarea | Estado |
|-------|--------|
| 1 — Inicialización del proyecto | ✅ Completada |
| 2 — Base de datos y modelos | ✅ Completada |
| 3 — Health check de la API | ✅ Completada |
| 4 — Crear ticket | ✅ Completada |
| 5 — Consultar y listar tickets | ✅ Completada |
| 6 — Editar ticket | ✅ Completada |
| 7 — Consultar un ticket individual | ✅ Completada |
| 8 — Usuarios y asignación | ✅ Completada |
| 9 — Comentarios | ✅ Completada |
| 10 — Búsqueda y filtros | ✅ Completada |
| 11 — Frontend: listado | ✅ Completada |
| 12 — Frontend: crear ticket | ✅ Completada |
| 13 — Frontend: detalle y gestión | ✅ Completada |
| 14 — Frontend: historial | ✅ Completada |
| 15 — Docker | ⬜ Pendiente |
| 16 — Documentación final | ⬜ Pendiente |
| 17 — Push a GitHub | ⬜ Pendiente (requiere autorización) |
| 18 — Máquina de estados (RF3) | ⬜ Pendiente |
