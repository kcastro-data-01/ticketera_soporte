# Ticketera de Soporte

Sistema de gestión de tickets de soporte desarrollado como práctica de Pasantes de Inteligencia Artificial.

**Objetivo:** registrar, priorizar, asignar y dar seguimiento a solicitudes de
soporte mediante una API REST y una interfaz web sencilla: crear tickets con
categoría y prioridad, asignarlos a una persona, comentarlos, buscarlos y
filtrarlos, y consultar su historial de cambios.

## Requisitos funcionales

- Crear un ticket con título y descripción.
- Seleccionar categoría y prioridad.
- Cambiar el estado entre **Nuevo**, **En proceso**, **Resuelto** y **Cerrado**:
  tocando el estado en el recorrido del detalle, con motivo
  opcional que queda como comentario. Se puede saltar pasos hacia adelante
  (p. ej. `Nuevo → Cerrado`) y reabrir `Resuelto → En proceso`. `Cerrado` es
  un estado final: no se reabre.
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

- Tres roles: Administrador, Técnico y Solicitante. Editar, asignar, eliminar,
  métricas y usuarios son solo del Administrador. Al arrancar, una migración
  pasa a Técnico a quien todavía tenga el rol Supervisor, que ya no existe
  (queda en el log), y la API responde `422` si se intenta usar.
- Permisos por rol: el servidor aplica la tabla de permisos (ver
  `ayuda.html`) y la interfaz oculta los botones y menús que el rol no puede
  usar. El Solicitante solo ve, comenta y consulta el historial de los tickets
  que creó (`tickets.created_by_id`, migración automática al arrancar).

- Panel de inicio con resumen (Nuevos, En proceso, Resueltos, Críticos sin
  resolver, Asignados a mí; `GET /api/tickets/summary`), vista «Mis tickets»
  (`?mios=true`) y paginación de 20 en 20 (`limit`/`offset`, total en la
  cabecera `X-Total-Count`).
- Inicio de sesión **solo con la cuenta de Microsoft de la empresa**
  (Entra ID); ver [Inicio de sesión con Microsoft](#inicio-de-sesión-con-microsoft).
  «Mi cuenta» muestra los datos del usuario (la contraseña es la de Microsoft).
- Desactivar/reactivar usuarios desde Usuarios (`is_active` en
  `PATCH /api/users/{id}`; `GET /api/users?todos=true` para el admin). Un
  usuario desactivado no inicia sesión y pierde la sesión abierta.
- No hay registro público: la cuenta se crea sola al entrar por primera vez
  con Microsoft (como Solicitante, o Administrador si es `ADMIN_INICIAL`) o
  cuando el dueño del buzón le envía un correo que se vuelve ticket (queda
  como asignado). Escribir al buzón sin cuenta no la crea: se le pide entrar
  primero con Microsoft.

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
  -d '{"name": "Ana Pérez", "email": "ana@soporte.local", "role": "Técnico"}'

curl http://127.0.0.1:8000/api/users
```

`POST /api/users` (`password` es opcional: se entra con Microsoft; solo se
usa con `LOGIN_LOCAL=true`, de 6 a 72 caracteres, y `PATCH /api/users/{id}`
la acepta para restablecerla) devuelve `201` con `{id, name, email, role}` (si `role`
se omite, se guarda `Técnico`). Errores:
`422` si `name` está vacío, el `email` no tiene formato válido o el `role` no
es `Administrador`/`Técnico`/`Solicitante`; `409 Conflict` si el email ya está registrado.
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

## Limpiar los datos de prueba

Antes de empezar a usar la ticketera en la empresa se pueden borrar los datos
de prueba con un comando:

```bash
docker compose exec ticketera python -m backend.limpiar_datos
# fuera de Docker: python -m backend.limpiar_datos
```

1. Si el usuario de `ADMIN_INICIAL` no existe (o la variable está vacía),
   avisa y no hace nada: es el único usuario que se conserva. Entra primero
   con esa cuenta de Microsoft para que se cree.
2. Copia la base a `/data/respaldo-antes-de-limpiar-<fecha-hora>.db` (fuera
   de Docker, si no hay `/data`, en la carpeta de la base) y muestra la ruta.
3. Pide escribir `BORRAR`. Con cualquier otra respuesta no borra nada (el
   respaldo queda igual).
4. Borra tickets, comentarios, historial, explicaciones de IA y todos los
   usuarios excepto `ADMIN_INICIAL`, y muestra cuántos tickets, comentarios y
   usuarios se borraron.

Se conservan los correos procesados (`processed_emails`, con `ticket_id` en
`NULL`), para que los correos viejos del buzón no vuelvan a crear tickets, y
la sesión de Microsoft del buzón (`/data/msal_cache.json`). Los demás usuarios
se vuelven a crear solos al entrar con Microsoft o al escribir al buzón, como
Solicitantes.

**Volver al respaldo.** Detén la app, pon el respaldo en el lugar de la base y
vuelve a arrancarla (cambia el nombre por el que mostró el comando):

```bash
docker compose stop ticketera
docker compose run --rm --no-deps --entrypoint sh ticketera -c \
  'cp /data/respaldo-antes-de-limpiar-20261023-153000.db /data/ticketera.db'
docker compose start ticketera
```

Fuera de Docker es lo mismo con `cp respaldo-antes-de-limpiar-….db ticketera.db`
con la API apagada.

## Métricas

El menú **«Métricas»** (`metricas.html`) lo ve solo el
**Administrador**; a los demás roles no les aparece y la API les responde `403`.
Todos los números los calcula el servidor (sin IA) y se filtran por un rango de
días en hora de Costa Rica (por defecto, los últimos 30 días contando hoy;
máximo 366).

Tarjetas:

- **Abiertos hoy** (Nuevo + En proceso) y **En proceso hoy**: la cola actual,
  sin importar el rango.
- **Resueltos en el período**: tickets cuyo primer paso a «Resuelto» cae en el
  rango (un Cerrado cuenta, porque antes pasó por Resuelto).
- **Tiempo promedio de resolución**: de esos tickets, desde que se crearon hasta
  ese primer «Resuelto» (por ejemplo «1 d 4 h»).
- **Por correo / por web**: tickets creados en el rango que llegaron del buzón
  de soporte frente al resto (los anteriores a la lectura del correo cuentan
  como web).

Gráficos (cada uno con su tabla en «Ver datos»):

- **Por estado** y **por categoría**: tickets creados en el rango, según su
  estado y su categoría actuales.
- **Por persona asignada**: abiertos hoy y resueltos en el período, con el rol
  de cada persona («Carlos Solís (Técnico)») y una fila «Sin asignar». Los
  resueltos se cuentan a quien tiene el ticket asignado ahora.
- **Creados por día**, con los días sin tickets en 0.

Los gráficos usan Chart.js 4.4.1 desde cdnjs (versión fija, con hash de
integridad). Si el navegador no tiene internet, la página muestra las mismas
cifras en tablas. Los tickets eliminados no cuentan, porque se borran con su
historial.

API: `GET /api/metricas?desde=YYYY-MM-DD&hasta=YYYY-MM-DD` (ver
[docs/api.md](docs/api.md)).

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

Para usar Qwen en **Groq** (API gratuita, compatible con OpenAI; es lo que
usa Vercel), en el `.env`:

```
ASISTENTE_PROVEEDOR=groq
GROQ_API_KEY=gsk_...
```

La clave se crea gratis en <https://console.groq.com/keys>. `GROQ_MODELO`
elige el modelo (por defecto `qwen/qwen3.8-27b`, el único Qwen de Groq; está
en *Preview*, así que si Groq lo retira hay que poner otro de
<https://console.groq.com/docs/models>, por ejemplo `llama-3.3-70b-versatile`).
Funcionan el chat libre, la interpretación de preguntas mal escritas, la
redacción de respuestas y «Explicar con IA» (con `response_format` JSON y la
misma validación y reintento que con Qwen local). Cada petición espera como
máximo `GROQ_TIMEOUT` segundos (20 por defecto, tope 25), así «Explicar con
IA» con su reintento no pasa de los 60 s de la función de Vercel. Si se
acaba el límite del plan gratis (Groq responde `429`), el chat y «Explicar
con IA» muestran «La IA está ocupada, intente de nuevo en un minuto»; lo que
calcula el servidor (conteos, fichas, reglas) sigue respondiendo. Sin
`GROQ_API_KEY` la IA queda apagada (`ia_disponible: false`).

Para usar Claude en lugar de Qwen3, en el mismo `.env`:

```
ASISTENTE_PROVEEDOR=claude
ANTHROPIC_API_KEY=sk-ant-...
```

Para que un modelo pequeño responda bien y rápido:

- Las preguntas frecuentes («¿cuántos críticos hay?», «¿qué tickets están en
  proceso?», «¿mis tickets?», «¿en qué estado está el #5?») las responde el
  servidor al instante, sin IA, con datos exactos y la nota «Respuesta del
  sistema».
- También los conteos **por rol o por persona** (solo tickets sin resolver):
  «¿cuántos tickets tienen los técnicos?», «¿qué tickets tiene Carlos?»,
  «¿cuántos sin asignar?». La respuesta separa por persona y muestra su rol:
  «Hay 3 tickets sin resolver asignados a técnicos: Carlos Solís (Técnico)
  tiene 2 (#3, #5) y José Solano (Técnico) tiene 1 (#7).». Toleran errores
  comunes («ticketes», «tiketes», «asigandos», «tecnico», sin tildes). Cada rol
  cuenta solo lo que puede ver: el Solicitante, sus propios tickets.
- Las reglas toleran errores comunes en «cuántos» y «hay» («cuatos», «cunatos»,
  «cauntos», «ai», «ay»): «cuatos ticketes hay ?» da el total al instante.
- Si las reglas no reconocen la pregunta (por ejemplo, «tikets terminaos ?»),
  la IA solo la **clasifica** en un JSON con valores fijos (tipo, estado,
  período, persona, rol, ticket; `format` de Ollama) y el servidor calcula con
  las mismas funciones y permisos. Si el JSON no sirve, la persona o el ticket
  no existen o es otro tipo de pregunta, sigue la IA libre. Se apaga con
  `ASISTENTE_INTERPRETAR_CON_IA=false`.
- Los límites de la interpretación (10 s) y de la redacción (20 s) van en la
  propia petición a Ollama: al vencerse se cierra la conexión y el modelo deja
  de generar (Ollama atiende una petición a la vez; una abandonada haría
  esperar a la siguiente). Si la interpretación se pasa del tiempo, no se
  llama a la IA libre: se responde con la regla si había una o «La IA está
  ocupada, probá de nuevo en unos segundos.».
- La IA libre recibe igual los conteos por estado, con sus otros nombres
  («terminados» = resueltos o cerrados; «pendientes» = nuevos + en proceso),
  y hasta 2 tickets de ejemplo por grupo para que el prompt sea corto.
- Con poca memoria (por ejemplo, WSL con 2 GB) el sistema manda parte del
  modelo al swap y todo se vuelve mucho más lento. En Windows, subí la memoria
  de WSL en `%UserProfile%\.wslconfig` (`[wsl2]` y `memory=4GB`) y corré
  `wsl --shutdown`.
- A la IA, cada persona le llega con su rol: «asignado a Laura Méndez
  (Administrador)».
- Los saludos y agradecimientos («hola», «buenas tardes», «gracias», «ok») los
  responde el servidor, sin IA.
- Lo que escribe la IA nunca muestra nada interno: se quitan las etiquetas
  (`<datos_visibles>`…) y, si la respuesta hablaba de ellas, del prompt o de sus
  instrucciones, se usa la respuesta del sistema.
- Los nombres se reconocen aunque estén mal escritos («jsoe solano» = José
  Solano, «crlos» = Carlos): cada palabra se compara con nombres y apellidos
  (hasta 1 error en nombres de hasta 5 letras y 2 en los más largos; dos letras
  intercambiadas cuentan como uno). Si coinciden nombre y apellido es esa
  persona; si hay empate gana quien coincide mejor y, para contar tickets,
  quien puede tenerlos asignados antes que un Solicitante.
- Seguimientos: «y José?», «y los técnicos?», «y ayer?» repiten la consulta
  anterior del chat cambiando solo la persona, el rol o el período.
- Si la pregunta nombra a alguien que no existe (o que el rol no puede ver),
  responde «No encontré a esa persona. ¿Podés escribir su nombre completo?»: los
  conteos por persona nunca los da la IA libre.
- Las preguntas sobre el **contenido** de un ticket («¿cómo resuelvo el #5?»,
  «¿qué hago con este ticket?») van siempre a la IA, que
  recibe el título, la descripción (hasta 1500 caracteres), la categoría, la
  prioridad, el estado, el asignado y los últimos 5 comentarios. En el detalle
  de un ticket, el chat envía su número: «este ticket» funciona sin escribir
  «#N». La guía fija queda solo para cómo usar la app («¿cómo cierro un
  ticket?»).
- Si Ollama falla, tarda demasiado o responde vacío, el chat muestra «La IA
  no está disponible en este momento» (nunca un texto inventado) y el detalle
  queda en el registro: `docker compose logs ticketera | grep IA:`.
- Tiempo máximo de respuesta: 90 s (`QWEN_TIMEOUT` en `.env` para cambiarlo;
  conectar con Ollama, 5 s). Mientras espera, el chat muestra los puntos
  animados y no deja enviar otra pregunta; el resto de la página sigue usable.
- La respuesta aparece por partes (`POST /api/asistente/stream`, NDJSON) y
  los «#N» enlazan al detalle del ticket.
- Al arrancar, la aplicación carga el modelo en Ollama y hace una redacción de
  prueba para que la primera pregunta no espere. El modelo queda siempre
  cargado (`keep_alive` -1; qwen3:0.6b ocupa poca memoria).

En ambos casos la restricción por rol la aplica el servidor: el modelo solo
recibe los datos que el rol ya puede ver en la aplicación.

## Explicar con IA

En el detalle de un ticket, **Técnico y Administrador** tienen el
botón **«Explicar con IA»**. Interpreta el ticket con lo que trae y le dice al
técnico por dónde empezar, **sin preguntarle nada a la persona** (el equipo no
siempre puede preguntar). El panel muestra, con la nota «Generado por IA, revisalo antes de
usarlo»:

- Arriba de todo, la **explicación**: 2 a 4 oraciones con palabras de la IA,
  como las diría un compañero (quién reporta, qué le pasa y qué es lo más
  probable que esté ocurriendo), con la **certeza** («alta», «media» o «baja»)
  como etiqueta chica. Si la IA copia los campos del ticket como lista
  («Título: …») se le pide de nuevo.
- **Claridad** («poco detalle», «clara» o «confusa») y por qué. **La calcula el
  servidor, no la IA**:
  - *poco detalle*: menos de 15 palabras, o le faltan 3 o más de estos datos:
    qué equipo/programa, desde cuándo, qué error aparece, qué ya se intentó;
  - *confusa*: más de 120 palabras, u oraciones de más de 40 palabras en promedio;
  - *clara*: el resto.
- **Posibles causas** (máx. 3, de la más probable a la menos) y **Qué revisar
  primero** (máx. 4 pasos numerados que el técnico puede hacer solo). Son
  sugerencias según el tipo de problema; la IA no debe inventar datos de la
  persona.
- **Categoría y prioridad sugeridas**, con su razón (opcionales; nunca se
  aplican solas).

La última explicación se guarda: al abrir el ticket se muestra sin llamar a la
IA. Si el ticket cambió (título, descripción, categoría, prioridad, estado o
comentarios) aparece «El ticket cambió…» y «Explicar con IA» la genera de
nuevo; **«Volver a explicar»** fuerza una nueva en cualquier momento. Las
explicaciones guardadas con un formato anterior (con preguntas) no se muestran
y se generan de nuevo la próxima vez que se pidan.

Cómo se adapta a un modelo muy chico (`qwen3:0.6b`):

- JSON corto con **tres ejemplos completos** (entrada y salida) dentro del
  prompt: impresora que «no sirve», correo que no deja entrar y un ticket de
  red largo y confuso;
  Ollama recibe el esquema en `format`, `temperature` 0.1 y `think: false`.
- Si el ticket es largo, se mandan solo el título, los primeros y últimos
  párrafos de la descripción y los últimos 3 comentarios (no pasa de `num_ctx`).
- El servidor valida el JSON; si viene mal, reintenta una vez y, si vuelve a
  fallar, muestra «La IA no pudo generar una explicación válida». Si solo la
  categoría o la prioridad vienen mal, se descartan y el resto se muestra.
- Si un paso o una causa le pide al técnico preguntarle algo a la persona, se
  quita (si no queda ninguno, se reintenta). Con *poco detalle* la certeza
  queda siempre en «baja».
- Si Ollama no responde: «La IA no está disponible en este momento» (detalle en
  `docker compose logs ticketera | grep IA:`).
- El modelo se sigue eligiendo con `QWEN_MODELO`.

**Desde el chat**: «explicame el ticket #3», «qué pasa con el tiket 5», «de
qué trata este ticket», «resumí el #3» o «no entiendo el ticket #3» (también
con «tickete», «tiket», «tikete» o sin tildes) **no llaman a la IA**: el
servidor responde con la ficha del ticket (número, título, estado, prioridad,
categoría, quién lo reporta, a quién está asignado, cuándo se creó y los
primeros ~200 caracteres de la descripción). Al final, el equipo ve «Si
necesita más información, como las posibles causas y qué revisar primero,
abra el ticket y use «Explicar con IA».», con un enlace que abre el detalle en
la pestaña de la explicación (`detalle.html?id=N&pestana=ia`); el Solicitante
ve «Puede ver el detalle completo en el ticket.» con el enlace al detalle. Si
el ticket no existe o la persona no puede verlo, responde «No encontré el
ticket…». El chat no muestra la fuente debajo de cada mensaje (el campo
`fuente` sigue llegando del servidor y queda en el log).

API: `GET /api/tickets/{id}/explicacion` (la guardada, sin IA) y
`POST /api/tickets/{id}/explicacion[?regenerar=true]`.

Para probarla con el modelo real y tres tickets de ejemplo (impresora «no
sirve», correo y uno de red largo y confuso):

```bash
docker compose exec ticketera python -m backend.probar_explicar_ia
```

(con `--borrar` elimina los tickets de prueba al terminar).

## Inicio de sesión con Microsoft

Se entra **solo con la cuenta de Microsoft de la empresa** (Entra ID), con la
misma app registrada del correo (`CORREO_M365_TENANT` y
`CORREO_M365_CLIENT_ID`). No hay usuario y contraseña propios ni registro.

1. `login.html` tiene un solo botón, «Iniciar sesión con Microsoft». Usa
   MSAL.js (`@azure/msal-browser@4.30.0` desde jsDelivr, versión fija con hash
   de integridad) con el flujo de código con PKCE y los scopes `openid`,
   `profile`, `email` y `User.Read`.
2. El navegador manda el `id_token` a `POST /api/auth/microsoft`. El backend lo
   valida (`backend/services/login_microsoft.py`): firma con las claves
   públicas de Microsoft del tenant, audiencia = `CORREO_M365_CLIENT_ID`,
   emisor = el tenant, vencimiento y `tid` del tenant (solo cuentas de la
   empresa). Después entrega la sesión de la app como siempre (`/api/auth/me`).
3. Roles (`asignar_rol_inicial`, función aparte para sumar reglas por puesto o
   departamento): `ADMIN_INICIAL` entra **siempre** como Administrador;
   cualquier otra persona nueva se crea como **Solicitante** con su nombre y
   correo de Microsoft. Quien ya existe mantiene su rol (lo cambia un
   Administrador en Usuarios). Una cuenta desactivada no entra.

### Requisitos en Microsoft Entra ID

En la app registrada: plataforma **Aplicación de página única** con la URI de
redirección `http://localhost:8000/login.html` (o `APP_URL/login.html`) y el
permiso `User.Read` con consentimiento de administrador. No hace falta secreto.

### Configuración

```env
CORREO_M365_TENANT=<Tenant ID o dominio>
CORREO_M365_CLIENT_ID=<Client ID>
ADMIN_INICIAL=kcastro@data.cr
# Solo para desarrollo: también se puede entrar con correo y contraseña
LOGIN_LOCAL=false
```

`GET /api/auth/config` (público) le pasa a `login.html` el tenant, el client id
y si `LOGIN_LOCAL` está activo. Con `LOGIN_LOCAL=true` vuelve el formulario de
contraseña (`POST /api/auth/login`) y, en Usuarios, los campos de contraseña;
con `false` (por defecto) `/api/auth/login` no existe (404).

## Tickets por correo

La ticketera puede revisar un buzón (por ejemplo `kcastro@data.cr`) cada minuto
y crear un ticket con cada correo nuevo **que pida ayuda**. Los correos normales
de la empresa (reuniones, facturas…) no se tocan, no se guardan y no reciben
respuesta. Si el buzón es solo de soporte, `CORREO_FILTRO=todos` convierte cada
correo en ticket. Si el asunto empieza con **«Ticket:»** (sin importar
mayúsculas), el correo siempre crea un ticket y el título va sin «Ticket:».

**Filtro con IA (`CORREO_FILTRO=ia`, por defecto cuando hay IA configurada).**
En este orden:

1. Se ignoran siempre (también con «Ticket:» o en el hilo de un ticket): las
   respuestas automáticas que llegan (fuera de oficina, no entregado,
   `Auto-Submitted`), los avisos de cualquier ticketera (cabeceras o remitente
   de Zendesk, Jira, Freshdesk…, asunto «[Ticketera] …», frases como «agente
   virtual» o «le compartimos el resumen») y los boletines (`List-Unsubscribe`,
   `Precedence: bulk`).
2. «Ticket:» al inicio del asunto → ticket. Respuesta en el hilo de un ticket
   o «[Ticket #N]» → comentario.
3. Más de 3 destinatarios (Para + CC) o remitente de otro dominio → se ignora.
4. El resto lo decide la IA (`ASISTENTE_PROVEEDOR`, p. ej. Groq) con solo el
   asunto y los primeros 800 caracteres: es solicitud si reporta un problema
   técnico o pide ayuda, acceso o soporte; no lo es un resumen, un informe,
   la presentación de un proyecto (aunque hable de tickets), un saludo, un
   agradecimiento, una reunión o un envío de archivos.
5. Si la IA falla o llega a su límite (429), un filtro de palabras estricto
   (solo frases de un problema real, como «no puedo entrar» o «se dañó»;
   «ticket», «soporte» o «estado» sueltas no cuentan) y queda en el log
   «se usó el filtro de respaldo». Tras una falla la IA descansa 60 s.

En el log queda cada decisión («Correo aceptado/ignorado (ia: motivo)»),
sin el texto del correo. Los que la IA descarta quedan sin leer en la bandeja
y no se le vuelven a preguntar. El freno de 5 tickets por revisión sigue. El
aviso de «ingrese primero» a quien no tiene cuenta solo sale si su correo es
una solicitud.

Regla general: **quien escribe es el solicitante y quien recibe, el asignado**.
Los correos que llegan al buzón quedan asignados al dueño del buzón
(`CORREO_USUARIO`), sin reparto automático; los que el dueño envía, al
destinatario (ver «Correos enviados» más abajo). El historial del ticket dice
«Ticket creado desde correo enviado por <nombre> a <nombre>».

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
| Responde en el hilo de un correo que ya es ticket (In-Reply-To / References / `conversationId`) | Se agrega como **comentario** si es el solicitante, el asignado o **cualquier usuario activo que estuvo en el hilo** (en «Para» o CC). |
| Escribe «[Ticket #N]» (o «Ticket #N») en el asunto, sin responder en el hilo | Comentario solo si es el solicitante o el asignado de ese ticket (así nadie comenta un ticket ajeno con solo escribir el número). |
| Alguien sin cuenta del dominio de la empresa (`DOMINIO_EMPRESA`, p. ej. `data.cr`) | **No se crea ni el usuario ni el ticket.** Se le responde en el hilo: «Para crear tickets por correo, primero ingrese a la ticketera con su cuenta de Microsoft de la empresa: `APP_URL`. Después vuelva a enviar su solicitud.» (con `X-Auto-Response-Suppress` y `X-Ticketera`). El correo queda registrado (`sin_cuenta`), así no se le responde dos veces. Solo si el correo pasa el filtro: a un correo normal de un compañero sin cuenta no se le responde. |
| Alguien sin cuenta que responde en el hilo de un ticket | Se ignora (no comenta ni recibe el aviso). En el registro: `Comentario ignorado: <correo> no tiene cuenta en la ticketera (ticket #N)`. |
| Alguien sin cuenta de otro dominio (o sin `DOMINIO_EMPRESA`) | **Se ignora**: no se crea ticket ni se responde; se marca como leído y se mueve. En el registro: `Correo ignorado: remitente externo sin cuenta <correo>`. |
| Cuenta desactivada | Se le avisa que hable con un administrador. |
| Respuestas automáticas, rebotes, «noreply», o el propio buzón | Nunca se responden (evita bucles). |
| Responde o reenvía un aviso de la app («Ingrese a la ticketera para crear tickets», «No pudimos crear tu ticket», o un «Registrate para crear tickets» viejo), con o sin `RE:`/`RV:`/`FW:`/`Fwd:` | Se ignora: nunca crea un ticket. Se marca como leído y se mueve. |
| Responde a «Ticket #N creado», «Comentario agregado al ticket #N», «[Ticket #N] Se le asignó…» o «[Ticket #N] Nuevo comentario…» | Si puede comentar (ver arriba) y escribió algo, se agrega como **comentario**; si no, se ignora. Nunca crea un ticket nuevo. |
| Un aviso de la app que el buzón se mandó a sí mismo (p. ej. un comentario en un ticket asignado al dueño) | No se toca: queda sin leer en la bandeja para que el dueño lo vea. |

La app lee los correos **no leídos** de la bandeja de entrada con Microsoft
Graph. Cada correo que procesa se responde **en el mismo hilo**, se marca como
leído y se mueve a la carpeta **Tickets-Procesados** (se crea sola). Los que
no piden ayuda se quedan sin leer en la bandeja. Solo se procesan los correos
que llegan después de activar la función.

### Correos enviados

La app también revisa **Elementos enviados** del buzón (mismo permiso
`Mail.ReadWrite`). Con `CORREO_FILTRO=auto` o `todos`, lo que envía el dueño a
alguien de la empresa crea un ticket **solo si el asunto empieza con
«Ticket:»** (el título va sin «Ticket:»). Con `CORREO_FILTRO=ia` pasan por el mismo filtro que la bandeja:
primero se ignoran los automáticos, los avisos de cualquier ticketera (también
los de esta), los boletines, los de más de 3 destinatarios y los que van solo a
externos; «Ticket:» crea siempre y una respuesta en el hilo de un ticket es
comentario; el resto lo decide la IA (asunto + 800 caracteres): ticket solo si
el dueño le reporta a un compañero un problema técnico o le pide soporte,
acceso o ayuda; no si es coordinación, un saludo, un envío de archivos, una
reunión, un agradecimiento, un resumen o un informe. Si la IA falla, el filtro
estricto de respaldo. En el log queda «Enviado aceptado/ignorado (ia: motivo)»
sin el texto, y cuentan para el freno de 5 tickets por revisión.

| Caso | Qué pasa |
|---|---|
| Asunto «Ticket: …» y va a alguien de `DOMINIO_EMPRESA` en «Para» | Ticket a nombre del dueño, **asignado al primer destinatario de la empresa en «Para»** (CC no cuenta). Si no tiene cuenta, se crea con el nombre del encabezado y el correo en minúsculas; cuando entre con Microsoft, el login lo encuentra por correo y usa ese mismo usuario y ve el ticket. |
| Responde en el hilo de un ticket (o con «Ticket #N» en uno donde participa) | Comentario del dueño en ese ticket. Nunca crea otro. |
| Va solo a externos, solo al propio buzón, o solo en CC a la empresa | Se ignora. |
| Lo envió la ticketera (registrado como `aviso_app` al enviarlo, cabecera `X-Ticketera`, asunto o frases fijas de sus avisos) | Se ignora. |
| Su conversación ya se procesó | Se ignora: nunca crea un ticket nuevo. |
| El asunto no empieza con «Ticket:» | No crea ticket (queda anotado y no se revisa otra vez). |

### Protección contra ciclos de correos

- Todo correo que envía la app (confirmaciones, «Se le asignó…», «Nuevo
  comentario…», «Ingrese a la ticketera…») se crea primero como borrador
  (`createReply` o `POST /me/messages`), se **registra** en
  `processed_emails` con su Message-ID, su `conversationId` y el ticket del
  que habla (`result = aviso_app`) y recién después se envía (`/send`). Si no
  se puede registrar, no se envía. Su copia en Elementos enviados o en la
  bandeja ya no se procesa como correo nuevo.
- Si Graph no conserva la cabecera `X-Ticketera`, el aviso se reconoce por el
  asunto (también con «RE:») y por las frases fijas del texto. Un correo con
  esa cabecera o esas frases que llega de otra persona (por ejemplo, de la
  ticketera de un compañero) tampoco crea un ticket.
- Un correo de una conversación ya procesada nunca crea un ticket nuevo: es
  un comentario (si responde en el hilo de un ticket) o se ignora. Responder a
  una confirmación o a un aviso agrega un comentario.
- **Freno**: en una revisión del buzón (cron o hilo) se crean como máximo 5
  tickets (`MAX_TICKETS_POR_CICLO`); los demás correos quedan sin leer y sin
  registrar para la revisión siguiente, y el log muestra «ALERTA: freno de
  seguridad del correo…».

**Cómo se reconoce el hilo** (en la bandeja y en enviados), en este orden:
cabeceras In-Reply-To / References, el `conversationId` de Graph (se guarda en
`processed_emails.conversation_id`) y «Ticket #N» en el asunto. Comprobado con
el buzón real: en los correos recibidos Graph trae In-Reply-To y References en
`internetMessageHeaders`; en Elementos enviados no (ahí solo están las
cabeceras `X-…` de quien envía), así que se leen de las propiedades
extendidas de Exchange; `conversationId` viene siempre. Graph también conserva
la cabecera `X-Ticketera` de las confirmaciones; las enviadas antes de usarla
se reconocen por el asunto.

Cada enviado queda registrado por su `Message-ID` (nunca crea dos tickets). Los
enviados **no se mueven ni se marcan**, y solo cuentan los enviados después de
activar la función (marca `__inicio_enviados__` en `processed_emails`). Con
`AVISAR_ASIGNADO=true` se le envía al asignado un correo «Se le asignó el
ticket #N» con el enlace a `APP_URL` y «[Ticket #N]» en el asunto (si responde,
la respuesta vuelve como comentario). Apagado por defecto mientras `APP_URL`
sea `localhost`.

### Avisos de comentarios hechos en la app

Con `AVISAR_COMENTARIOS=true`, cuando alguien agrega un comentario **desde la
app**, el solicitante y el asignado reciben «[Ticket #N] Nuevo comentario en el
ticket #N» con el texto, quién lo escribió y el enlace (menos quien lo
escribió). Si responden, la respuesta vuelve como comentario. Los comentarios
que **llegan por correo no avisan** (así no se arma un ciclo). Si el envío
falla, el comentario se guarda igual y el error queda en el registro
(`No se pudo avisar por correo el comentario del ticket #N`). Por defecto está
encendido en Vercel y apagado en Docker. Funciona igual en modo `hilo` y
`cron`: el aviso sale en la misma petición del comentario.

El asignado ve el ticket en su lista aunque sea **Solicitante**, lo comenta y
le cambia el estado (solo en los tickets asignados a él); no lo edita,
reasigna ni borra.

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
DOMINIO_EMPRESA=data.cr
APP_URL=http://IP-O-NOMBRE-DEL-EQUIPO:8000
```

Opcionales: `CORREO_CARPETA_PROCESADOS` (por defecto `Tickets-Procesados`),
`CORREO_FILTRO` (`ia`, `auto` o `todos`; si no está, `ia` cuando hay IA y si
no `auto`), `CORREO_INTERVALO` (segundos, 60),
`AVISAR_ASIGNADO` (`false`; `true` avisa por correo al asignado de un ticket
creado desde un correo enviado), `AVISAR_COMENTARIOS` (`false` en Docker,
`true` en Vercel: avisa por correo los comentarios hechos en la app) y
`CORREO_M365_CACHE` (archivo de la caché de tokens de antes; en Docker es
`/data/msal_cache.json`). Los tokens ahora se guardan en la base de datos
(tabla `msal_cache`); si la tabla está vacía y ese archivo existe, se importa
solo una vez y no hace falta volver a iniciar sesión. El archivo no se borra.

### Primer inicio de sesión

```bash
docker compose up -d --build
docker compose exec ticketera python -m backend.correo_login
```

Muestra un código: ábrelo en <https://microsoft.com/devicelogin>, escribe el
código y entra con la cuenta del buzón. Los tokens quedan en la base de datos
y la app los renueva sola; no hace falta reiniciar. Sin Docker: `python -m backend.correo_login`.

Para ver qué está pasando:

```bash
docker compose logs ticketera | grep CORREO
```

Si aparece «sesión de Microsoft no iniciada o vencida», vuelve a ejecutar
`correo_login` (pasa si se cambió la contraseña de la cuenta, se revocó la
sesión o estuvo apagada mucho tiempo). La app no se cae: sigue intentando
cada minuto.

## Publicar en Vercel

La misma app corre en Docker (SQLite + Ollama, como siempre) y en Vercel
(<https://tickets-americandata.vercel.app>, plan gratis). Se elige por
variables de entorno; Vercel define `VERCEL=1` solo, y con eso cambian estos
valores por defecto (cada uno se puede forzar con su variable):

| | Docker | Vercel |
|---|---|---|
| Base de datos (`DATABASE_URL`) | SQLite en el volumen | Postgres en Neon |
| IA (`ASISTENTE_PROVEEDOR`) | `qwen` | `ninguno` (apagada); `groq` para tenerla gratis |
| Correo (`CORREO_MODO`) | `hilo`: revisa cada `CORREO_INTERVALO` s | `cron`: lo llama cron-job.org |
| Caché de tokens del buzón | tabla `msal_cache` | tabla `msal_cache` |
| `/docs` y `/openapi.json` | visibles | apagados |
| Contraseña (`LOGIN_LOCAL`) | según `.env` | siempre apagada |

Archivos: `vercel.json` (frontend estático desde `frontend/`, `/api/*` y
`/health` a la función `api/index.py`, encabezado `X-Robots-Tag: noindex`),
`.vercelignore` y `.python-version`. Docker no los usa.

Con `ASISTENTE_PROVEEDOR=groq` y `GROQ_API_KEY` la IA funciona en Vercel
igual que en Docker, con Qwen en Groq (ver «Asistente de IA»). Con la IA apagada el chat sigue respondiendo lo que calcula el servidor
(conteos, fichas de tickets, fecha y hora…); lo que iría a la IA libre
contesta que el chat libre no está disponible. En el detalle del ticket no
aparece el botón «Explicar con IA» (si hay una explicación copiada de Docker,
se ve, sin «Volver a explicar»).

### Pasos, en orden

1. **Código en GitHub.** Mergear la rama a `main` y subirla (Vercel publica
   cada push a `main`; los demás pushes crean *previews*).
2. **Proyecto en Vercel.** *Add New → Project →* importar el repositorio,
   nombre `tickets-americandata`, *Framework Preset: Other*. No tocar los
   comandos (los define `vercel.json`).
3. **Base Neon.** En el proyecto: *Storage → Create Database → Neon* (o
   *Marketplace → Neon*) y conectarla al proyecto. Crea `DATABASE_URL`
   (con pooler, la usa la app) y `DATABASE_URL_UNPOOLED` (sin pooler, para
   copiar datos y para `correo_login` desde la compu). Dejarla conectada solo
   al entorno **Production**.
4. **Variables** (*Settings → Environment Variables*, entorno
   **Production** solamente, así los previews no tocan la base ni el buzón):

   | Variable | Valor |
   |---|---|
   | `JWT_SECRET_KEY` | aleatoria (ver abajo). Sin ella la app no arranca |
   | `CRON_SECRET` | otra aleatoria |
   | `CORREO_M365_TENANT` | el mismo de `.env` (GUID del tenant o `data.cr`) |
   | `CORREO_M365_CLIENT_ID` | el mismo de `.env` |
   | `ADMIN_INICIAL` | `kcastro@data.cr` |
   | `DOMINIO_EMPRESA` | `data.cr` |
   | `CORREO_ACTIVO` | `1` |
   | `CORREO_USUARIO` | el buzón de soporte |
   | `CORREO_FILTRO` | `ia` (necesita `ASISTENTE_PROVEEDOR=groq` y `GROQ_API_KEY`; sin IA usa el filtro estricto) |
   | `CORREO_CARPETA_PROCESADOS` | `Tickets-Procesados` |
   | `AVISAR_ASIGNADO` | `true` (ya hay un enlace público) |
   | `AVISAR_COMENTARIOS` | `true` (ya es el valor por defecto en Vercel; queda explícito) |
   | `APP_URL` | `https://tickets-americandata.vercel.app` |
   | `ASISTENTE_PROVEEDOR` | `groq` (sin ella la IA queda apagada) |
   | `GROQ_API_KEY` | la clave de <https://console.groq.com/keys> (secreta) |
   | `GROQ_MODELO` | opcional; por defecto `qwen/qwen3.8-27b` |

   `DATABASE_URL` ya la puso Neon. Para generar las claves:
   `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
   Ningún secreto va al repositorio: `.env` y `.env.*` están en `.gitignore`.
5. **Apagar el correo en Docker** antes de copiar (y dejarlo apagado mientras
   Vercel lea el buzón): en `.env`, `CORREO_ACTIVO=0` y
   `docker compose up -d ticketera`. Si los dos leen el mismo buzón se crean
   tickets y respuestas repetidos.
6. **Copiar los datos de Docker a Neon** (con la imagen nueva:
   `docker compose up -d --build ticketera`). La cadena va en una variable
   para que no quede en el historial:

   ```bash
   read -rs DESTINO_URL   # pegar DATABASE_URL_UNPOOLED de Neon y Enter
   export DESTINO_URL
   docker compose exec -e DESTINO_URL ticketera python -m backend.copiar_a_postgres
   unset DESTINO_URL
   ```

   Muestra cuántas filas hay en cada tabla en origen y destino. Si Neon ya
   tiene datos no copia nada (`--reemplazar` los borra y copia de nuevo).
   Copia también los tokens del buzón: si ya estaban en Docker, el paso 7 se
   puede saltar.
7. **Primer inicio de sesión del buzón contra Neon** (desde la compu, con
   device code). Crear `.env.neon` (ignorado por Git) con:

   ```
   DATABASE_URL=<DATABASE_URL_UNPOOLED de Neon>
   ```

   y ejecutar:

   ```bash
   docker run --rm -it --env-file .env --env-file .env.neon \
     ticketera_soporte-ticketera python -m backend.correo_login
   ```

   Abrir <https://microsoft.com/devicelogin>, escribir el código y entrar con
   el buzón. Los tokens quedan en Neon; Vercel los lee y los renueva solo.
   Repetirlo solo si el cron empieza a responder «La sesión del buzón no está
   iniciada o venció» (contraseña cambiada, sesión revocada, ~90 días sin uso).
8. **Microsoft Entra ID.** *App registrations →* la app de la ticketera *→
   Authentication →* en la plataforma **Single-page application** agregar la
   URI `https://tickets-americandata.vercel.app/login.html` (dejar la de
   `http://localhost:8000/login.html` para Docker) y guardar. En *Overview*,
   *Supported account types* tiene que ser «Accounts in this organizational
   directory only». El backend además rechaza invitados (otro `idp`) y
   correos que no sean `@data.cr`.
9. **Redeploy** (*Deployments → … → Redeploy*) para que tome las variables.
   Probar: entrar con Microsoft, ver el tablero, abrir un ticket, preguntar
   en el chat «¿cuántos tickets nuevos hay?».
10. **cron-job.org.** *Create cronjob*:
    * URL: `https://tickets-americandata.vercel.app/api/cron/correo`
    * *Advanced → Request method:* `POST`
    * *Advanced → Headers:* `Authorization` = `Bearer <CRON_SECRET>`
    * *Schedule:* cada minuto (ver el límite de Neon abajo: conviene solo en
      horario laboral, p. ej. lunes a viernes de 7 a 19, y un segundo cronjob
      cada 15 minutos fuera de ese horario).
    * *Notifications:* avisar si falla.

    Con *Test run* tiene que responder `200` y
    `{"estado": "ok", "conteo": {…}}`. `401`: el encabezado no coincide con
    `CRON_SECRET`; `404`: falta `CRON_SECRET` en Vercel; `503`: correo
    apagado o sesión del buzón vencida (paso 7).

### Lo que no funciona igual que en Docker

* **IA:** sin «Explicar con IA», sin chat libre y sin redacción ni
  interpretación con IA (siempre las respuestas fijas del sistema).
* **Correo:** como máximo una revisión por minuto (la que dispara
  cron-job.org), de hasta ~25 s: si llegan muchos correos juntos, se reparten
  en varios minutos (`pendientes` en la respuesta). Si cron-job.org falla, no
  se leen correos. El aviso «correo ignorado» del log se repite en cada
  revisión (no hay memoria entre llamadas).
* **Neon gratis:** 0,5 GB de datos. La base se suspende tras 5 minutos sin uso
  y la primera consulta tarda ~1 s más. Un cron cada minuto la mantiene
  despierta todo el día y puede gastar las horas de cómputo gratis del mes:
  revisar el consumo en la consola de Neon y, si hace falta, usar el horario
  laboral del paso 10.
* **Vercel Hobby:** la primera petición después de un rato tarda 1–3 s
  (arranque en frío); los logs duran poco; no hay disco (todo va a Neon);
  límites mensuales de invocaciones y CPU (el cron usa ~43 000 llamadas al
  mes). Los términos del plan Hobby son para uso **no comercial**: para la
  empresa correspondería el plan Pro.
* **Datos separados:** Docker (SQLite) y Vercel (Neon) son bases distintas.
  El código se edita en Docker y llega a Vercel al subir a `main`; los datos
  no viajan entre una y otra.
