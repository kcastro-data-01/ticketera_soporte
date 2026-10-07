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
│   │   ├── comentarios.py
│   │   └── catalogos.py
│   ├── services/
│   │   ├── ticket_service.py     # lógica + transiciones de estado
│   │   └── historial_service.py  # registro de auditoría
│   └── tests/
│       ├── conftest.py
│       ├── test_models.py
│       ├── test_constants.py
│       ├── test_smoke.py
│       ├── test_tickets.py
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
        ├── api.js
        ├── listado.js
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
GET    /api/tickets                 ?q=&state=&category=&priority=&assigned_to=&page=&size=
POST   /api/tickets
GET    /api/tickets/{id}
PUT    /api/tickets/{id}            (title, description, category, priority)
PATCH  /api/tickets/{id}/state      {state, reason?}
PATCH  /api/tickets/{id}/assign     {user_id}
POST   /api/tickets/{id}/comments
GET    /api/tickets/{id}/comments
GET    /api/tickets/{id}/history
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
- **Objetivo:** asignar/desasignar tickets.
- **Archivos:** `backend/routers/tickets.py` (`PATCH /api/tickets/{id}/assign`),
  `backend/services/ticket_service.py`, `backend/tests/test_asignacion.py`.
- **Prueba:** `pytest` — asigna, reasigna (historial), desasigna,
  usuario inválido → 404.
- **Criterio de terminado:** la asignación funciona de extremo a extremo y
  queda auditada.

### Tarea 9 — Comentarios (RF5)
- **Objetivo:** conversación sobre el ticket.
- **Archivos:** `backend/routers/comentarios.py`,
  `backend/tests/test_comentarios.py`.
- **Prueba:** `pytest` — agrega, lista en orden cronológico, contenido vacío →
  422, ticket inexistente → 404.
- **Criterio de terminado:** los comentarios persisten y el historial los
  menciona.

### Tarea 10 — Búsqueda y filtros de tickets (RF7, RF8)
- **Objetivo:** endpoint central de consulta.
- **Archivos:** `backend/routers/tickets.py`, `backend/services/ticket_service.py`,
  `backend/tests/test_busqueda_filtro.py`.
- **Prueba:** `pytest` — cada filtro aislado, filtros combinados, búsqueda
  parcial, paginación sin repetidos ni huecos.
- **Criterio de terminado:** todos los escenarios de filtrado probados.

### Tarea 11 — Frontend: listado con búsqueda y filtros
- **Objetivo:** primera pantalla funcional.
- **Archivos:** `frontend/index.html`, `frontend/css/estilos.css`,
  `frontend/js/api.js`, `frontend/js/listado.js`, `backend/main.py` (estáticos).
- **Prueba:** manual en navegador + `pytest` en verde.
- **Criterio de terminado:** se puede buscar y filtrar desde la UI.

### Tarea 12 — Frontend: crear ticket
- **Objetivo:** alta desde la interfaz.
- **Archivos:** `frontend/crear.html`, `frontend/js/crear.js`, `index.html`.
- **Prueba:** manual — crear válido, crear inválido muestra errores.
- **Criterio de terminado:** el alta funciona desde la UI y los errores se
  muestran.

### Tarea 13 — Frontend: detalle, estados, asignación, comentarios
- **Objetivo:** toda la gestión de un ticket.
- **Archivos:** `frontend/detalle.html`, `frontend/js/detalle.js`.
- **Prueba:** manual — transición inválida no se ofrece, asignación y
  comentarios funcionan.
- **Criterio de terminado:** todos los flujos de gestión funcionan desde la UI.

### Tarea 14 — Frontend: historial de cambios
- **Objetivo:** visualizar la auditoría.
- **Archivos:** `frontend/detalle.html`, `frontend/js/detalle.js`,
  `frontend/css/estilos.css`.
- **Prueba:** manual — cada tipo de cambio aparece reflejado.
- **Criterio de terminado:** el historial se ve completo y legible.

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
| 8 — Usuarios y asignación | ⬜ Pendiente |
| 9 — Comentarios | ⬜ Pendiente |
| 10 — Búsqueda y filtros | ⬜ Pendiente |
| 11 — Frontend: listado | ⬜ Pendiente |
| 12 — Frontend: crear ticket | ⬜ Pendiente |
| 13 — Frontend: detalle y gestión | ⬜ Pendiente |
| 14 — Frontend: historial | ⬜ Pendiente |
| 15 — Docker | ⬜ Pendiente |
| 16 — Documentación final | ⬜ Pendiente |
| 17 — Push a GitHub | ⬜ Pendiente (requiere autorización) |
| 18 — Máquina de estados (RF3) | ⬜ Pendiente |
