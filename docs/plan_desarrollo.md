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
│       ├── test_tickets.py
│       ├── test_estados.py
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

_Implementado en la Tarea 2. Identificadores (tablas, columnas, relaciones) en
inglés según la decisión de idioma; los valores guardados en `category`,
`priority` y `state` son los textos en español de `backend/constants.py` porque
se muestran en la interfaz._

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

### Tarea 3 — Esquemas Pydantic y app FastAPI mínima
- **Objetivo:** app arrancable con validación de entrada/salida.
- **Archivos:** `backend/schemas.py`, `backend/main.py`,
  `backend/routers/catalogos.py`, `backend/tests/test_smoke.py`.
- **Prueba:** `uvicorn backend.main:app` responde; `pytest` del smoke test;
  `GET /docs` accesible.
- **Criterio de terminado:** la app arranca y OpenAPI muestra los endpoints de
  catálogo.

### Tarea 4 — Crear ticket (RF1, RF2)
- **Objetivo:** alta de tickets con validación.
- **Archivos:** `backend/routers/tickets.py`, `backend/services/ticket_service.py`,
  `backend/tests/test_tickets.py`.
- **Prueba:** `pytest` — creación OK (201), campos inválidos → 422,
  categoría desconocida → 422.
- **Criterio de terminado:** se crea y consulta un ticket con todos los campos
  y las pruebas pasan.

### Tarea 5 — Historial de cambios (RF9)
- **Objetivo:** auditoría enganchada a todas las mutaciones.
- **Archivos:** `backend/services/historial_service.py`,
  `backend/routers/tickets.py` (GET historial), `backend/tests/test_historial.py`.
- **Prueba:** `pytest` — al crear un ticket aparece 1 entrada; al modificar un
  campo se registra valor anterior/nuevo.
- **Criterio de terminado:** toda creación queda registrada y el endpoint
  devuelve el historial ordenado.

### Tarea 6 — Editar ticket
- **Objetivo:** actualización con registro en historial.
- **Archivos:** `backend/routers/tickets.py`, `backend/services/ticket_service.py`,
  `backend/tests/test_tickets.py`.
- **Prueba:** `pytest` — actualiza, historial registra campo/anterior/nuevo,
  404 si no existe.
- **Criterio de terminado:** la edición funciona y el historial refleja
  exactamente los cambios.

### Tarea 7 — Máquina de estados (RF3)
- **Objetivo:** transiciones válidas con historial.
- **Archivos:** `backend/services/ticket_service.py`,
  `backend/routers/tickets.py` (`PATCH /estado`), `backend/tests/test_estados.py`.
- **Prueba:** `pytest` — transición válida OK; `Nuevo → Cerrado` → 409;
  `Cerrado` terminal; historial correcto.
- **Criterio de terminado:** todas las transiciones cubiertas por pruebas.

### Tarea 8 — Usuarios y asignación (RF4)
- **Objetivo:** asignar/desasignar tickets.
- **Archivos:** `backend/routers/tickets.py` (`PATCH /asignar`),
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

### Tarea 10 — Listado, búsqueda y filtros (RF6, RF7, RF8)
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

## Estado del avance

| Tarea | Estado |
|-------|--------|
| 1 — Inicialización del proyecto | ✅ Completada |
| 2 — Base de datos y modelos | ✅ Completada |
| 3 — Esquemas Pydantic y app mínima | ⬜ Pendiente |
| 4 — Crear ticket | ⬜ Pendiente |
| 5 — Historial de cambios | ⬜ Pendiente |
| 6 — Editar ticket | ⬜ Pendiente |
| 7 — Máquina de estados | ⬜ Pendiente |
| 8 — Usuarios y asignación | ⬜ Pendiente |
| 9 — Comentarios | ⬜ Pendiente |
| 10 — Listado, búsqueda y filtros | ⬜ Pendiente |
| 11 — Frontend: listado | ⬜ Pendiente |
| 12 — Frontend: crear ticket | ⬜ Pendiente |
| 13 — Frontend: detalle y gestión | ⬜ Pendiente |
| 14 — Frontend: historial | ⬜ Pendiente |
| 15 — Docker | ⬜ Pendiente |
| 16 — Documentación final | ⬜ Pendiente |
| 17 — Push a GitHub | ⬜ Pendiente (requiere autorización) |
