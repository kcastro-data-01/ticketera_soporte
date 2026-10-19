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
  y consulta de comentarios y lectura del historial de cambios.
- Frontend (servido por la misma aplicación): listado con búsqueda y filtros,
  creación de tickets, pantalla de detalle con edición, asignación,
  cambio de estado, listado y creación de comentarios y consulta de
  historial, y administración de usuarios (alta y listado con navegación
  entre páginas); las fechas y horas se muestran en hora local de Costa
  Rica (`America/Costa_Rica`, UTC-6) a partir de marcas de tiempo en UTC
  con desplazamiento explícito.
- Ejecución local y con Docker (`docker compose up --build`), con persistencia
  de SQLite en un volumen.
- Suite de pruebas con pytest (294 pruebas), pruebas del frontend con
  `node:test` (52 pruebas en cuatro ficheros) y documentación en
  [docs/api.md](docs/api.md).

- Permisos por rol: el servidor aplica la tabla de permisos (ver
  `ayuda.html`) y la interfaz oculta los botones y menús que el rol no puede
  usar. El Solicitante solo ve, comenta y consulta el historial de los tickets
  que creó (`tickets.created_by_id`, migración automática al arrancar).

- Panel de inicio con resumen (Nuevos, En proceso, Resueltos, Críticos sin
  resolver, Asignados a mí; `GET /api/tickets/summary`), vista «Mis tickets»
  (`?mios=true`) y paginación de 20 en 20 (`limit`/`offset`, total en la
  cabecera `X-Total-Count`).
- «Mi cuenta»: cada usuario cambia su contraseña
  (`POST /api/auth/change-password`).
- Desactivar/reactivar usuarios desde Usuarios (`is_active` en
  `PATCH /api/users/{id}`; `GET /api/users?todos=true` para el admin). Un
  usuario desactivado no inicia sesión y pierde la sesión abierta.
- El registro público solo existe para crear el primer Administrador
  (`GET /api/auth/setup`); las demás cuentas las crea un Administrador.

- Asistente de IA (botón «Asistente» abajo a la derecha, `POST /api/asistente`):
  responde preguntas sobre la app con Claude. El servidor solo le entrega los
  datos que el rol puede ver (el Solicitante, solo sus tickets y nunca la lista
  de usuarios; los correos nunca se envían), así que no puede revelar
  información interna aunque se la pidan. Usa Qwen3 con Ollama (gratuito,
  incluido en `docker-compose.yml`) o, opcionalmente, Claude (ver «Asistente
  de IA» más abajo).

**Pendientes**

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

1. **Categorías fijas:** Hardware, Software, Red, Accesos.
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
  /api/tickets/{id}/assign`); si no hay usuarios, se muestra la nota
  «No hay usuarios disponibles. Puedes crear uno desde Usuarios» y el
  guardado queda bloqueado, y si `GET /api/users` falla se desactiva el
  selector con un error claro;
- **cambiar el estado** (`PATCH /api/tickets/{id}/state`): muestra el estado
  actual y solo ofrece los destinos posibles desde él — `Nuevo → En proceso →
  Resuelto → Cerrado` —, con confirmación si el cambio se aplica (`200`),
  mensaje del backend si la transición no está permitida (`409`) y una nota
  cuando el ticket está `Cerrado` (estado final, sin transiciones); el
  selector se desactiva en ese caso y el backend vuelve a validar siempre;
- **agregar y consultar comentarios** (`POST /api/tickets/{id}/comments` y
  `GET /api/tickets/{id}/comments`): lista los comentarios de más antiguo a
  más reciente con autor, hora local de Costa Rica y texto, con estados de
  carga, lista vacía y error diferenciados; al agregar un comentario, la
  lista se actualiza sola sin recargar la página;
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
    "category": "Hardware",
    "priority": "Alta"
  }'
```

Devuelve `201 Created` con el ticket creado (el estado inicial es `Nuevo`).
Categorías válidas: `Hardware`, `Software`, `Red`, `Accesos`.
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
| `category` | `Hardware`, `Software`, `Red`, `Accesos` | filtra por categoría |
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

`POST /api/users` (requiere `password`, de 6 a 72 caracteres, para que el
usuario pueda iniciar sesión; `PATCH /api/users/{id}` acepta `password` para
restablecerla) devuelve `201` con `{id, name, email, role}` (si `role`
se omite, se guarda `Técnico`). Errores:
`422` si `name` está vacío, el `email` no tiene formato válido o el `role` no
es `Administrador`/`Supervisor`/`Técnico`/`Solicitante`; `409 Conflict` si el email ya está registrado.
`GET /api/users` devuelve `200` con los usuarios **activos** disponibles
para asignar (solo lectura, orden por id).

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

Al arrancar también se ejecutan migraciones incrementales e idempotentes.
La de categorías (`backend/migrate_categories.py`) reconstruye la tabla
`tickets` —SQLite no permite alterar un `CHECK`— y traduce los valores
antiguos con la correspondencia aprobada 1 a 1: `Incidente → Hardware`,
`Consulta → Software`, `Solicitud → Accesos`, `Mantenimiento → Red`. Se
conservan todos los datos de los tickets (incluidas sus fechas) y sus
comentarios e historial; los tickets creados después solo aceptan las
categorías vigentes.

### Pruebas

```bash
.venv/bin/python -m pytest -q
# o, con pytest instalado en el entorno activo:
pytest

# Pruebas del frontend (Node.js, sin dependencias):
node --test frontend/tests/app_errors.test.js
node --test frontend/tests/detalle_flujo.test.js
node --test frontend/tests/usuarios_ui.test.js
```

La suite completa (294 pruebas) usa bases de datos temporales por test y no
modifica `ticketera.db`. Las pruebas del frontend (52 en total) cargan los
scripts reales en un contexto aislado con `node:test`:
`frontend/tests/app_errors.test.js` (10) verifica el manejo de errores de
`fetchTickets()` (conexión, error HTTP, respuesta inválida y casos de
éxito), comprobando en cada caso que una ejecución realiza exactamente una
petición HTTP; `frontend/tests/detalle_flujo.test.js` (20) cubre la hora
de Costa Rica en el detalle y el listado, el listado de comentarios
(carga, vacío, errores y refresco tras agregar) y la asignación de
usuarios (detalle del backend, desasignación, usuarios no disponibles y
lista vacía); `frontend/tests/usuarios_ui.test.js` (13) cubre el listado
de usuarios (éxito, vacío y errores), las validaciones del formulario
(nombre, correo y rol) y el alta (éxito con recarga, email duplicado y
datos inválidos); y `frontend/tests/historial_ui.test.js` (9) cubre la
pantalla de historial global: que la petición se envía con `fetchWithAuth`
y el Bearer token de la sesión (regresión del 401 sin token), el pintado
de las siete columnas con el autor real, los estados vacío/error HTTP/
JSON inválido/sin conexión y la limpieza de sesión ante un 401.

### Documentación de la API

El detalle de cada endpoint (método, parámetros, body, respuestas, errores y
ejemplos), junto con el mapeo RF1–RF9 y la lista de lo **no implementado**,
está en [docs/api.md](docs/api.md). La documentación interactiva se sirve en
`/docs` con la aplicación arrancada.

## Eliminar tickets

Solo el **Administrador** puede eliminar un ticket: en el detalle del ticket
aparece el botón **Eliminar** (los demás roles no lo ven, y la API les responde
`403`). Antes de borrar se pide confirmación («¿Seguro que querés eliminar el
ticket #N? Esta acción no se puede deshacer.») y después se vuelve al listado.

- API: `DELETE /api/tickets/{id}` → `204` si se eliminó, `403` si el rol no es
  Administrador, `404` si el ticket no existe.
- Se borran el ticket, sus comentarios y su historial en una sola transacción
  (si algo falla, no se borra nada).
- Si el ticket vino por correo, el registro de ese correo se conserva sin
  ticket: así el mismo correo nunca vuelve a crear un ticket.
- Como el historial desaparece con el ticket, queda constancia en el registro
  de la aplicación: `docker compose logs ticketera | grep TICKETS`
  (por ejemplo, `TICKETS: Laura Méndez (laura.mendez@adn.local, id 1) eliminó el
  ticket #6 «…» el 2026-10-19 15:30 UTC`).

## Plan de desarrollo

El desarrollo se realiza estrictamente por tareas. El plan completo está en
[docs/plan_desarrollo.md](docs/plan_desarrollo.md).


## Asistente de IA

Por defecto el asistente usa **Qwen3** ([QwenLM/Qwen3](https://github.com/QwenLM/Qwen3)),
un modelo abierto y gratuito que corre en tu propia computadora con
[Ollama](https://ollama.com): no necesita clave ni cobra por consulta.
`docker compose up --build -d` levanta tres servicios:

- `ticketera`: la aplicación.
- `ollama`: el servidor de modelos.
- `ollama-descarga`: descarga `qwen3:0.6b` (unos 0,5 GB) la primera vez y
  termina. Mientras descarga, el chat avisa que el modelo aún no está listo;
  el progreso se ve con `docker compose logs -f ollama-descarga`.

Por defecto se usa `qwen3:0.6b`, el más liviano (unos 2 GB de RAM libres),
para que funcione en computadoras modestas sin trabarlas. Sus respuestas son
más simples. Con más memoria puedes usar uno más capaz creando un archivo
`.env` junto a `docker-compose.yml`:

| Modelo | Disco | RAM libre aprox. |
|---|---|---|
| `qwen3:0.6b` (por defecto) | 0,5 GB | 2 GB |
| `qwen3:1.7b` | 1,4 GB | 3-4 GB |
| `qwen3:4b` | 2,5 GB | 6-8 GB |

```
QWEN_MODELO=qwen3:1.7b
```

y ejecutando `docker compose up -d` (descarga el modelo nuevo). Para borrar
un modelo que ya no uses: `docker compose exec ollama ollama rm qwen3:4b`.
Si usas Docker Desktop en Windows, la memoria disponible para Docker se
ajusta en Settings → Resources.

Para usar Claude en lugar de Qwen3, en el mismo `.env`:

```
ASISTENTE_PROVEEDOR=claude
ANTHROPIC_API_KEY=sk-ant-...
```

Para que un modelo pequeño responda bien y rápido:

- Las preguntas frecuentes («¿cuántos críticos hay?», «¿qué tickets están en
  proceso?», «¿mis tickets?», «¿en qué estado está el #5?») las responde el
  servidor al instante, sin IA, con datos exactos.
- Si la pregunta nombra un ticket («explícame el #5»), el modelo recibe su
  descripción, últimos comentarios y último cambio.
- La respuesta aparece por partes (`POST /api/asistente/stream`, NDJSON) y
  los «#N» enlazan al detalle del ticket.
- Al arrancar, la aplicación precarga el modelo en Ollama para que la primera
  pregunta no espere.

En ambos casos la restricción por rol la aplica el servidor: el modelo solo
recibe los datos que el rol ya puede ver en la aplicación.

## Tickets por correo

La ticketera puede revisar un buzón (por ejemplo `kcastro@data.cr`) cada minuto
y crear un ticket con cada correo nuevo **que pida ayuda**. Los correos normales
de la empresa (reuniones, facturas…) no se tocan, no se guardan y no reciben
respuesta. Si el buzón es solo de soporte, `CORREO_FILTRO=todos` convierte cada
correo en ticket.

### ¿Cómo se decide que un correo «pide ayuda»?

Por **palabras clave** (`SEÑALES_SOPORTE` en `backend/services/correo_service.py`).
Se buscan en el asunto **y** en el texto **nuevo** del correo (el campo
`uniqueBody` de Graph; lo citado o reenviado de mensajes anteriores no cuenta),
en minúsculas y sin tildes; basta con que aparezca una:

| Tipo | Frases |
|---|---|
| Pedido directo | soporte, ayuda, ayudarme / ayudarnos («ticket» no cuenta: aparece en los correos de la propia app) |
| «No …» | no (me/nos/le) funciona, sirve, enciende, prende, arranca, abre, carga, imprime, conecta, deja, responde, aparece, llega, reconoce, suena |
| «No puedo …» | no puedo / podemos / logro + entrar, ingresar, abrir, imprimir, conectar, acceder, enviar, iniciar, trabajar, instalar, usar, ver |
| «Se …» | se (me/nos/le) dañó, dañaron, quebró, cayó, cayeron, trabó, pegó, congeló, apagó, reinicia, desconecta, bloqueó |
| Fallas | dañado/a, falla / falló / fallando, error(es), problema(s) con, arreglar…, reparar… |
| Equipos y accesos | impresora, contraseña, clave, bloqueado/a, internet, wifi, vpn, sin red / conexión / internet / sistema, lento/a + la/el/mi, computadora, laptop, monitor, teclado, mouse, instalar, licencia, acceso |

Si ninguna aparece, el correo queda sin leer en la bandeja y el registro dice
`Correo ignorado: no parece solicitud de ayuda «asunto»` (una vez por correo).
Si un correo de soporte real no se detecta, agrega la frase a la lista.

| Quién escribe (correo que pide ayuda) | Qué pasa |
|---|---|
| Usuario activo de la ticketera (mismo correo) | Se crea el ticket a su nombre (asunto = título, cuerpo = descripción, categoría y prioridad por palabras clave) y se le responde con el número y el enlace. |
| Responde a «Ticket #N» de un ticket suyo | Se agrega como comentario a ese ticket. |
| Alguien sin cuenta | **No se crea ticket.** Se le responde con el asunto «Registrate para crear tickets», que explica que primero cree su cuenta en `APP_URL/login.html?registro=1&email=…` y después vuelva a enviar su solicitud. Máximo un aviso cada 24 h por remitente; el correo igual se marca como leído y se mueve. En el registro: `Correo ignorado: remitente no registrado <correo>`. |
| Cuenta desactivada | Se le avisa que hable con un administrador. |
| Respuestas automáticas, rebotes, «noreply», o el propio buzón | Nunca se responden (evita bucles). |
| Responde o reenvía un aviso de la app («Registrate para crear tickets», «No pudimos crear tu ticket»), con o sin `RE:`/`RV:`/`FW:`/`Fwd:` | Se ignora: nunca crea un ticket. Se marca como leído y se mueve. |
| Responde a «Ticket #N creado» o «Comentario agregado al ticket #N» | Si es el dueño del ticket y escribió algo, se agrega como **comentario**; si no, se ignora. Nunca crea un ticket nuevo. |

La app lee los correos **no leídos** de la bandeja de entrada con Microsoft
Graph. Cada correo que procesa se responde **en el mismo hilo**, se marca como
leído y se mueve a la carpeta **Tickets-Procesados** (se crea sola). Los que
no piden ayuda se quedan sin leer en la bandeja. Solo se procesan los correos
que llegan después de activar la función. Cualquiera puede registrarse en
`login.html`; esas cuentas siempre quedan como **Solicitante**.

### Requisitos en Microsoft Entra ID (Azure)

App registrada con:

- Permisos **delegados** de Microsoft Graph: `Mail.ReadWrite`, `Mail.Send` y
  `User.Read` (con consentimiento concedido).
- *Authentication* → **Permitir flujos de clientes públicos = Sí** (el inicio
  de sesión es con código de dispositivo; no hay secreto de cliente).

### Configuración

En el archivo `.env` (copia de `.env.example`, no se sube a Git):

```env
CORREO_ACTIVO=1
CORREO_USUARIO=kcastro@data.cr
CORREO_M365_TENANT=<Tenant ID>
CORREO_M365_CLIENT_ID=<Client ID>
APP_URL=http://IP-O-NOMBRE-DEL-EQUIPO:8000
```

Opcionales: `CORREO_CARPETA_PROCESADOS` (por defecto `Tickets-Procesados`),
`CORREO_FILTRO` (`auto` o `todos`), `CORREO_INTERVALO` (segundos, 60) y
`CORREO_M365_CACHE` (archivo de la caché de tokens; en Docker es
`/data/msal_cache.json`, dentro del volumen `ticketera-data`; fuera de Docker,
`.msal_cache.json` en la raíz, ignorado por Git).

### Primer inicio de sesión

```bash
docker compose up -d --build
docker compose exec ticketera python -m backend.correo_login
```

Muestra un código: ábrelo en <https://microsoft.com/devicelogin>, escribe el
código y entra con la cuenta del buzón. Los tokens quedan en la caché y la app
los renueva sola; no hace falta reiniciar. Sin Docker: `python -m backend.correo_login`.

Para ver qué está pasando:

```bash
docker compose logs ticketera | grep CORREO
```

Si aparece «sesión de Microsoft no iniciada o vencida», vuelve a ejecutar
`correo_login` (pasa si se cambió la contraseña de la cuenta, se revocó la
sesión o estuvo apagada mucho tiempo). La app no se cae: sigue intentando
cada minuto.
