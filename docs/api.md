# API — Ticketera de Soporte

Documentación de los endpoints **realmente implementados** en el código
(`backend/routers/`). La referencia interactiva de Swagger queda en
`http://127.0.0.1:8000/docs` y el esquema OpenAPI en
`http://127.0.0.1:8000/openapi.json` con la aplicación arrancada.

**Condiciones generales**

- **Base URL (local):** `http://127.0.0.1:8000` · **(Docker):**
  `http://localhost:8000`.
- **Sin autenticación** (decisión aprobada 2): no existen tokens, sesiones ni
  cabeceras de autorización; los usuarios solo sirven para asignación y firma
  de comentarios/historial.
- **Formato:** JSON. Identificadores de campos en inglés; los valores de los
  enums (`Hardware`, `Nuevo`, `Alta`…) llegan en español tal como los muestra
  la interfaz.
- **Fechas:** ISO-8601 en UTC con desplazamiento explícimo (`...Z`, p. ej.
  `2026-10-07T19:29:19.391813Z`) en `created_at`, `updated_at` y
  `created_at` de historial/comentarios; la interfaz las muestra en hora
  local de Costa Rica (`America/Costa_Rica`, UTC-6) sin desfases.

## Resumen de endpoints

| Método | Ruta | Propósito |
|--------|------|-----------|
| `GET` | `/health` | Estado del servicio |
| `POST` | `/api/tickets` | Crear un ticket |
| `GET` | `/api/tickets` | Listar, buscar y filtrar tickets |
| `GET` | `/api/tickets/{ticket_id}` | Consultar un ticket |
| `PATCH` | `/api/tickets/{ticket_id}` | Editar título/descripción/categoría/prioridad |
| `PATCH` | `/api/tickets/{ticket_id}/assign` | Asignar o desasignar un usuario |
| `PATCH` | `/api/tickets/{ticket_id}/state` | Cambiar el estado (máquina de estados) |
| `DELETE` | `/api/tickets/{ticket_id}` | Eliminar un ticket (solo Administrador) |
| `GET` | `/api/tickets/{ticket_id}/explicacion` | Última explicación de la IA (sin generar) |
| `POST` | `/api/tickets/{ticket_id}/explicacion` | Explicar el ticket con IA (`?regenerar=true` fuerza una nueva) |
| `GET` | `/api/metricas` | Métricas de tickets para Supervisor y Administrador (`?desde=&hasta=`) |
| `POST` | `/api/tickets/{ticket_id}/comments` | Agregar un comentario |
| `GET` | `/api/tickets/{ticket_id}/comments` | Listar comentarios (cronológico) |
| `GET` | `/api/tickets/{ticket_id}/history` | Historial de cambios (solo lectura) |
| `POST` | `/api/users` | Crear un usuario |
| `GET` | `/api/users` | Listar usuarios |

## Objetos comunes

**Ticket** (`TicketResponse`):

```json
{
  "id": 1,
  "title": "No enciende la impresora",
  "description": "La impresora del piso 2 no responde desde ayer.",
  "category": "Hardware",
  "priority": "Alta",
  "state": "Nuevo",
  "assigned_to_id": null,
  "created_at": "2026-10-07T19:29:19.391813Z",
  "updated_at": "2026-10-07T19:29:19.391813Z"
}
```

**Enums:** `category` ∈ `Hardware | Software | Red | Accesos`;
`priority` ∈ `Baja | Media | Alta | Crítica`;
`state` ∈ `Nuevo | En proceso | Resuelto | Cerrado`.

**Errores:** el cuerpo usa `{"detail": "..."}` (mensaje legible) y, en `422`,
una lista de objetos `{loc, msg, type}` propia de FastAPI/Pydantic.

**Códigos habituales:** `200` OK · `201` creado · `404` recurso inexistente ·
`409` conflicto (email duplicado de usuario o transición de estado no
permitida) · `422` datos inválidos.

---

## Salud

### `GET /health`

Comprueba que la API está viva. Sin parámetros ni body.

- `200` → `{"status": "ok"}`

```bash
curl http://127.0.0.1:8000/health
```

---

## Tickets

### `POST /api/tickets`

Crea un ticket (RF1, RF2). El estado inicial es `Nuevo` y no se envía en el
body.

**Body** (JSON, obligatorio):

| Campo | Tipo | Reglas |
|-------|------|--------|
| `title` | string | 3–200 caracteres tras recortar espacios |
| `description` | string | no puede quedar vacía |
| `category` | enum | uno de los valores de `category` |
| `priority` | enum | uno de los valores de `priority` |

**Respuestas:** `201` con el ticket creado · `422` si falta un campo, el
título tiene < 3 o > 200 caracteres, la descripción está vacía o un enum no es
válido.

```bash
curl -X POST http://127.0.0.1:8000/api/tickets \
  -H "Content-Type: application/json" \
  -d '{"title": "No enciende la impresora", "description": "No responde desde ayer.", "category": "Hardware", "priority": "Alta"}'
```

### `GET /api/tickets`

Lista todos los tickets, **de más reciente a más antiguo** (RF6), con búsqueda
(RF7) y filtros (RF8). Todos los parámetros son opcionales y se combinan con
AND; sin parámetros devuelve el listado completo. Si no hay resultados,
responde `200` con `[]`.

**Parámetros de consulta:**

| Parámetro | Valores | Efecto |
|-----------|---------|--------|
| `search` | texto libre | coincidencia parcial (case-insensitive) en `title` o `description`; vacío o solo espacios equivale a no enviado; `%` y `_` se tratan como texto literal |
| `category` | `Hardware`, `Software`, `Red`, `Accesos` | filtra por categoría |
| `priority` | `Baja`, `Media`, `Alta`, `Crítica` | filtra por prioridad |
| `state` | `Nuevo`, `En proceso`, `Resuelto`, `Cerrado` | filtra por estado |

**Respuestas:** `200` con la lista de tickets · `422` si un parámetro de enum
no es válido. No existe paginación ni ordenamiento configurable.

```bash
curl "http://127.0.0.1:8000/api/tickets?search=correo&priority=Alta&state=Nuevo"
```

### `GET /api/tickets/{ticket_id}`

Devuelve un ticket por su id (solo lectura).

- `200` → el ticket · `404` → `{"detail": "Ticket 999 no encontrado"}`

### `PATCH /api/tickets/{ticket_id}`

Edición **parcial** de los datos básicos (RF1, RF2): solo `title`,
`description`, `category` y `priority`. Los campos `id`, `state`,
`assigned_to_id` y `created_at` **no** se pueden modificar con este endpoint;
`updated_at` se actualiza automáticamente.

**Body:** al menos uno de los cuatro campos (mismas reglas de validación que
la creación).

**Respuestas:** `200` con el ticket actualizado · `404` si no existe · `422`
si un valor es inválido o el body no contiene ningún campo modificable
(mensaje: *"la petición debe incluir al menos un campo a modificar"*).

```bash
curl -X PATCH http://127.0.0.1:8000/api/tickets/1 \
  -H "Content-Type: application/json" \
  -d '{"priority": "Crítica"}'
```

### `PATCH /api/tickets/{ticket_id}/assign`

Asigna un usuario al ticket o lo desasigna (RF4).

**Body:**

| Campo | Tipo | Reglas |
|-------|------|--------|
| `assigned_to_id` | integer \| null | obligatorio; `null` desasigna; si no es `null` debe existir el usuario |

**Respuestas:** `200` con el ticket actualizado · `404` si no existe el
ticket (`Ticket N no encontrado`) o el usuario (`Usuario N no encontrado`) ·
`422` si falta el campo.

```bash
curl -X PATCH http://127.0.0.1:8000/api/tickets/1/assign \
  -H "Content-Type: application/json" \
  -d '{"assigned_to_id": 1}'
```

### `DELETE /api/tickets/{ticket_id}`

Elimina el ticket con sus comentarios y su historial en una sola transacción.
Solo para el rol **Administrador**. El registro del correo que creó el ticket
(si vino por correo) se conserva con `ticket_id` en `null`, para que ese correo
no vuelva a crear un ticket. Quién eliminó qué ticket y cuándo queda en el log
de la aplicación (`TICKETS: …`).

| Código | Cuándo |
|--------|--------|
| `204` | Eliminado (sin cuerpo) |
| `401` | Sin sesión |
| `403` | El rol no es Administrador |
| `404` | El ticket no existe |

```bash
curl -X DELETE http://localhost:8000/api/tickets/6 -H "Authorization: Bearer $TOKEN"
```

### `GET` / `POST /api/tickets/{ticket_id}/explicacion`

«Explicar con IA», para Técnico, Supervisor y Administrador (Solicitante:
`403`). `GET` devuelve la explicación guardada sin llamar a la IA
(`explicacion: null` si nunca se explicó). `POST` la reutiliza si el ticket no
cambió; si cambió, o con `?regenerar=true`, la pide a la IA y la guarda.

```json
{
  "ticket_id": 7,
  "claridad": "poco detalle",
  "motivo_claridad": "La descripción tiene 2 palabras y no dice: …",
  "explicacion": {
    "explicacion": "Laura Méndez reporta que una impresora no funciona …",
    "posibles_causas": ["…"],
    "que_revisar_primero": ["…"],
    "certeza": "baja",
    "categoria_sugerida": {"valor": "Hardware", "razon": "…"},
    "prioridad_sugerida": null
  },
  "vigente": true,
  "generada_en": "2026-10-19T16:00:00Z",
  "modelo": "qwen3:0.6b",
  "desde_cache": false
}
```

`claridad` la calcula el servidor. `explicacion.explicacion` es el texto
narrado (2 a 4 oraciones); `posibles_causas` (máx. 3) y `que_revisar_primero`
(máx. 4) no incluyen preguntas para la persona; `certeza` es `alta`, `media` o
`baja` (siempre `baja` con «poco detalle»). Las explicaciones guardadas con un
formato anterior se devuelven como `null` y el `POST` las genera de nuevo. `502` si la IA no está disponible o si
devolvió dos veces un JSON inválido; `404` si el ticket no existe.

### `GET /api/metricas`

Solo **Supervisor y Administrador** (Técnico y Solicitante: `403`; sin sesión:
`401`). Lo calcula el servidor, sin IA. `desde` y `hasta` son días
`YYYY-MM-DD` en hora de Costa Rica, con los dos extremos incluidos; por
defecto, los últimos 30 días hasta hoy. `422` si `desde` es posterior a `hasta`,
si el rango pasa de 366 días o si una fecha está mal escrita.

```json
{
  "desde": "2026-09-20",
  "hasta": "2026-10-19",
  "tarjetas": {
    "abiertos": 12, "en_proceso": 5,
    "resueltos_periodo": 30, "tiempo_promedio_horas": 26.5,
    "creados_periodo": 41, "por_correo": 9, "por_web": 32
  },
  "por_estado": [{"nombre": "Nuevo", "total": 7}],
  "por_categoria": [{"nombre": "Hardware", "total": 10}],
  "por_persona": [{"id": 3, "nombre": "Carlos Solís", "rol": "Técnico", "activo": true,
                   "abiertos": 4, "resueltos": 9}],
  "sin_asignar_abiertos": 2,
  "por_dia": [{"fecha": "2026-09-20", "total": 0}]
}
```

`abiertos` y `en_proceso` (y `abiertos` por persona, y `sin_asignar_abiertos`)
son la cola de hoy. El resto usa el rango: `por_estado`, `por_categoria`,
`por_dia` y el origen cuentan los tickets **creados** en el rango;
`resueltos_periodo`, `resueltos` por persona y `tiempo_promedio_horas` (`null`
si no hay resueltos) usan el primer paso a «Resuelto» de cada ticket.
`por_estado` y `por_categoria` incluyen todos los valores, aunque estén en 0.

### `PATCH /api/tickets/{ticket_id}/state`

Cambia el estado del ticket a través de la máquina de estados (RF3). Solo se
aceptan los avances lineales; no hay saltos, retrocesos ni transiciones
automáticas, y `Cerrado` es un estado final. Cada cambio exitoso registra
**exactamente una** entrada en `history` (`action` = `"Cambio de estado"`,
`field` = `"state"`, `old_value`/`new_value` con los estados, `author` =
nombre del usuario autenticado y `author_id` = su id) en la misma operación
de base de datos que la actualización del ticket. Una transición rechazada no
toca el ticket ni el historial.

**Transiciones permitidas:**

| Desde | Hasta |
|-------|-------|
| `Nuevo` | `En proceso` |
| `En proceso` | `Resuelto` |
| `Resuelto` | `Cerrado` |

Todo lo demás queda fuera: saltos (`Nuevo → Resuelto`), retrocesos
(`En proceso → Nuevo`), mantener el mismo estado (`Nuevo → Nuevo`) y
cualquier cambio sobre `Cerrado`.

**Body** (JSON, obligatorio):

| Campo | Tipo | Reglas |
|-------|------|--------|
| `state` | enum | uno de los valores de `state`; debe ser un destino permitido desde el estado actual |

**Respuestas:**

- `200` → el ticket con el estado nuevo y `updated_at` actualizado.
- `404` → `{"detail": "Ticket 999 no encontrado"}` si el ticket no existe.
- `409` → `{"detail": "Transición de 'Nuevo' a 'Resuelto' no permitida"}`
  cuando la transición no está permitida (incluye mantener el mismo estado).
- `422` → si falta `state` o el valor no pertenece al enum.

```bash
curl -X PATCH http://127.0.0.1:8000/api/tickets/1/state \
  -H "Content-Type: application/json" \
  -d '{"state": "En proceso"}'
```

```json
{
  "id": 1,
  "title": "No enciende la impresora",
  "description": "La impresora del piso 2 no responde desde ayer.",
  "category": "Hardware",
  "priority": "Alta",
  "state": "En proceso",
  "assigned_to_id": null,
  "created_at": "2026-10-07T19:29:19.391813Z",
  "updated_at": "2026-10-08T12:00:00.000000Z"
}
```

---

## Usuarios

### `POST /api/users`

Crea el usuario mínimo usado para asignación y firma (sin autenticación).

**Body:**

| Campo | Tipo | Reglas |
|-------|------|--------|
| `name` | string | obligatorio, no vacío, máx. 120 |
| `email` | string | formato de email válido, máx. 255, **único** |
| `password` | string | obligatorio, entre 6 y 72 caracteres; se guarda cifrada y nunca se devuelve |
| `role` | enum | `Administrador` \| `Supervisor` \| `Técnico` \| `Solicitante`; opcional, por defecto `Técnico` |

**Respuestas:** `201` con `{id, name, email, role}` · `422` si `name` está
vacío, el email no cumple el formato, la contraseña falta o no cumple el largo,
o el rol no es válido · `409 Conflict` si
el email ya está registrado.

```bash
curl -X POST http://127.0.0.1:8000/api/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token de un Administrador>" \
  -d '{"name": "Ana Pérez", "email": "ana.perez@tec.local", "password": "clave2026", "role": "Técnico"}'
```

### `GET /api/users`

Devuelve los usuarios **activos** disponibles para asignar tickets (solo
lectura, orden por id). Los usuarios inactivos no se listan.

- `200` → lista de usuarios; `[]` si no hay.

---

## Comentarios

### `POST /api/tickets/{ticket_id}/comments`

Agrega un comentario a un ticket existente (RF5).

**Body:**

| Campo | Tipo | Reglas |
|-------|------|--------|
| `content` | string | obligatorio, no vacío, máx. 2000 caracteres |
| `author` | string | opcional (por defecto `"Anónimo"`), no vacío, máx. 120 |

**Respuestas:** `201` con `{id, ticket_id, author, content, created_at}` ·
`404` si el ticket no existe · `422` si `content` o `author` son inválidos.

```bash
curl -X POST http://127.0.0.1:8000/api/tickets/1/comments \
  -H "Content-Type: application/json" \
  -d '{"content": "Hola, ¿hay novedades?"}'
```

### `GET /api/tickets/{ticket_id}/comments`

Devuelve los comentarios guardados del ticket, de más antiguo a más reciente
(`created_at` con `id` como desempate), sin paginación (RF5, solo lectura).

- `200` → lista de `{id, ticket_id, author, content, created_at}`; `[]` si
  el ticket no tiene comentarios.
- `404` si el ticket no existe.

```bash
curl http://127.0.0.1:8000/api/tickets/1/comments
```

---

## Historial

### `GET /api/tickets/{ticket_id}/history`

Devuelve las entradas de auditoría del ticket en la tabla `history`, de más
antigua a más reciente (`created_at` con `id` como desempate), sin paginación
(RF9, solo lectura).

Cada entrada contiene exactamente los campos del modelo:
`id`, `ticket_id`, `action`, `field`, `old_value`, `new_value`, `author`,
`author_id` y `created_at`. Los opcionales (`field`, `old_value`,
`new_value`, `author`, `author_id`) vienen en `null` cuando el registro no
los define.

**Autoría (auditoría con usuario):** cada evento escrito por la API (creación,
edición, asignación, cambio de estado y comentarios) firma la entrada con el
**usuario autenticado** que ejecutó la acción: `author` guarda su nombre y
`author_id` su id en `users`. Los registros antiguos, escritos antes de esta
auditoría, tienen `author` = `"Anónimo"` o `null` y `author_id` = `null`; la
interfaz los muestra como **"Sistema"** (nunca como "Anónimo") y no se
modifican ni se eliminan.

**Respuestas:** `200` con la lista · `200` con `[]` si el ticket no tiene
entradas · `404` si el ticket no existe.

> **Alcance de la escritura:** la escritura en `history` se hace siempre
> desde la capa de servicio, junto con la operación que origina el cambio
> (creación, edición, asignación, cambio de estado y comentarios), nunca
> desde el frontend.

```bash
curl http://127.0.0.1:8000/api/tickets/1/history
```

---

## Requisitos funcionales → implementación

| RF | Requisito | Endpoint(s) | Estado | Pruebas |
|----|-----------|-------------|--------|---------|
| RF1 | Crear ticket | `POST /api/tickets` | ✅ Implementado | `test_tickets.py` |
| RF2 | Categoría y prioridad | `POST/PATCH /api/tickets` | ✅ Implementado | `test_tickets.py`, `test_constants.py` |
| RF3 | Cambiar estado | `PATCH .../state` | ✅ Implementado | `test_estados.py` |
| RF4 | Asignar a una persona | `PATCH .../assign` | ✅ Implementado | `test_asignacion.py`, `test_users.py` |
| RF5 | Agregar comentarios | `POST .../comments` + `GET .../comments` | ✅ Implementado (creación y listado) | `test_comentarios.py` |
| RF6 | Listado | `GET /api/tickets` | ✅ Implementado | `test_tickets.py` |
| RF7 | Buscar | `GET /api/tickets?search=` | ✅ Implementado | `test_busqueda_filtro.py` |
| RF8 | Filtrar | `GET /api/tickets?category=&priority=&state=` | ✅ Implementado | `test_busqueda_filtro.py` |
| RF9 | Historial de cambios | `GET .../history` | ✅ Lectura y escritura implementadas; cada evento (creación, edición, asignación, cambio de estado, comentarios) firma con el usuario autenticado | `test_historial.py`, `test_historial_global.py`, `test_estados.py` |

Salud (`GET /health`), usuarios (`POST/GET /api/users`) y la configuración de
la base de datos también tienen cobertura (`test_smoke.py`,
`test_users.py`, `test_database_env.py`).

## No implementado (aún)

Para no confundir lo documentado arriba con lo que **no existe**:

- **Autenticación / autorización** — excluidas por decisión aprobada; no es
  un defecto pendiente.
- **Paginación y ordenamiento** — `GET /api/tickets` devuelve todo el
  resultado.
- **`GET /api/catalogs`** — previsto en el bosquejo original del plan de
  desarrollo, sin implementar.

La referencia histórica por tarea está en
[plan_desarrollo.md](plan_desarrollo.md).
