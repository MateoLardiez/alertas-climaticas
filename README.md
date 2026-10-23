# alertas-climaticas
Sistema de Alertas Climaticas. Servicio HTTP construido con Python, FastAPI y PostgreSQL que permite a los usuarios configurar alertas sobre sus campos y ser notificados cuando el pronostico de los proximos 7 dias supera el umbral definido.

## API

## Requerimientos

### Requerimientos Funcionales
- Un usuario debe poder cargar su campo con sus datos, asociandolo a una region (CRUD completo)
- Un usuario debe poder configurar las alertas que quiera sobre su campo (CRUD completo). Cada alerta tiene un tipo de evento climatico y un umbral de probabilidad
- El sistema debe evaluar periodicamente (background job) los datos meteorologicos de los proximos 7 dias contra los umbrales de cada alerta, y generar notificaciones cuando se superan
- Un usuario debe poder consultar sus notificaciones a traves de un endpoint y marcarlas como leidas

### Requerimientos No Funcionales
- **Sin duplicados:** una alerta no notifica dos veces el mismo evento del mismo dia, aunque el job se ejecute varias veces (idempotencia)
- **Sin falsos negativos:** si la probabilidad alcanza el umbral, se notifica
- **Seguro ante concurrencia:** dos ejecuciones simultaneas del job no generan notificaciones repetidas
- **Asincronico:** API y acceso a base de datos async (FastAPI + SQLAlchemy async)
- **Procesamiento desacoplado:** la evaluacion de alertas corre en un background job independiente de las requests, por lo que ningun endpoint espera a que se evalue
- **Validacion y errores claros:** umbral entre 0 y 100, tipos de evento validos, 404 cuando un recurso no existe
- **Reproducible:** migraciones con Alembic, tests automatizados y ejecucion con Docker

### Fuera de alcance
- Integracion con WhatsApp
- Autenticacion y autorizacion
- Ingesta real de datos meteorologicos (los datos se mockean)

## Decisiones Tomadas

La consigna deja varios puntos abiertos. Estas son las decisiones adoptadas:

| Tema | Decision | Justificacion |
|---|---|---|
| Ubicacion del campo | Cada campo pertenece a una **region**, no a coordenadas | Los servicios meteorologicos no tienen precision por lat/lon exactas, y modelar coordenadas agrega datos y logica innecesarios para este alcance |
| Horizonte de evaluacion | El job evalua **7 dias hacia adelante** e informa los dias en que se supera el umbral | Alineado con un pronostico semanal |
| Eventos soportados | Lluvia, helada, tormenta (rayos y granizo) y calor extremo | Cubren los riesgos agricolas principales. La lista final se fija al definir el esquema |
| Condicion de disparo | Se notifica cuando la probabilidad es **mayor o igual** al umbral | La consigna dice "a partir del cual desean ser notificados", lo que sugiere un umbral inclusivo |
| Granularidad de notificacion | Una notificacion por alerta y dia del evento | La clave unica (alerta, fecha) garantiza que no haya duplicados aunque el job corra varias veces |
| Recordatorios | No se reenvia el aviso a medida que el evento se acerca | El aviso del dia 6 no aporta informacion nueva respecto al del dia 7. Si el usuario recibe una notificación diaria por el mismo evento, aprende a ignorarlas Cada notificacion significa "hay algo nuevo" |
| Cambios en el pronostico | Si la probabilidad cambia despues de notificar, no se vuelve a avisar | Requeriria guardar el valor notificado y definir que es un cambio relevante. Queda como mejora futura |
| Valor informado | Probabilidad del evento | La consigna indica que los datos almacenados son probabilidades. Una mejora futura seria adaptar otro valor (ej: cantidad de milimetros de lluvia, temperatura, etc) |
| Usuarios | Identificados por un `user_id` simple, sin autenticacion | Fuera de alcance del challenge |
| Datos meteorologicos | Mockeados mediante seed | La consigna indica que la ingesta ya existe |
| Notificacion al usuario | El job genera la notificacion en la base de datos. El usuario puede hacer una consulta por endpoint, sin integracion con WhatsApp | Lo indica la consigna |

## Modelo de Datos

![Diagrama del modelo de datos](dbdiagram.png)

El codigo DBML que genera el diagrama esta al final de este documento ([Anexo](#anexo-codigo-dbml)).

| Tabla | Columnas | Restricciones |
|---|---|---|
| `region` | `id` UUID PK, `name` | `name` unico |
| `users` | `id` UUID PK, `name` | |
| `farm` | `id` UUID PK, `user_id` FK, `region_id` FK, `name` | |
| `event` | `id` UUID PK, `name` | `name` unico |
| `weather_forecast` | `id` UUID PK, `region_id` FK, `event_id` FK, `forecast_date` DATE, `probability` SMALLINT | unico `(region_id, event_id, forecast_date)`, `CHECK` de 0 a 100 |
| `alert` | `id` UUID PK, `farm_id` FK, `event_id` FK, `threshold` SMALLINT | unico `(farm_id, event_id)`, `CHECK` de 0 a 100 |
| `notification` | `id` UUID PK, `alert_id` FK, `forecast_date` DATE, `probability` SMALLINT, `read_at` TIMESTAMPTZ nulo, `created_at` TIMESTAMPTZ | unico `(alert_id, forecast_date)` |

### Decisiones del modelo
- **UUID como clave primaria:** para parecerse a un entorno de produccion. Se generan con `gen_random_uuid()`, incluido en PostgreSQL desde la version 13.
- **Tabla `event` en lugar de enum:** agregar un tipo de evento es insertar una fila, sin migrar el esquema. Los eventos se identifican por `name` (unico).
- **`probability` y `threshold` como `SMALLINT`:** enteros de 0 a 100, sin `float`, para que la comparacion `>=` sea exacta.
- **`forecast_date` como `DATE`:** el pronostico es por dia calendario. Un `TIMESTAMP` obligaria a elegir una hora y una zona horaria, lo que puede correr el dia segun quien lo lea y romper la clave unica `(region_id, event_id, forecast_date)`.
- **`notification` guarda un snapshot de `probability`:** si el pronostico cambia despues, la notificacion enviada no se modifica.
- **`read_at` nulo en lugar de un boolean:** nulo significa "no leida" y ademas se sabe cuando se leyo.
- **Tabla `users` en plural:** `user` es palabra reservada en PostgreSQL.
- **Borrado:** eliminar una `farm` elimina en cascada sus alertas y notificaciones. Eliminar una `region` con campos asociados se rechaza (`RESTRICT`).

## Compilar y ejecutar

### Local

### Docker

## Estructura del Sistema


## Anexo: Codigo DBML

Codigo para regenerar el diagrama en [dbdiagram.io](https://dbdiagram.io/d).

```dbml
Table region {
  id uuid [pk, default: `gen_random_uuid()`]
  name varchar [not null, unique]
}

Table users {
  id uuid [pk, default: `gen_random_uuid()`]
  name varchar [not null]
}

Table event {
  id uuid [pk, default: `gen_random_uuid()`]
  name varchar [not null, unique]
}

Table farm {
  id uuid [pk, default: `gen_random_uuid()`]
  user_id uuid [not null]
  region_id uuid [not null]
  name varchar [not null]
}

Table weather_forecast {
  id uuid [pk, default: `gen_random_uuid()`]
  region_id uuid [not null]
  event_id uuid [not null]
  forecast_date date [not null]
  probability smallint [not null]

  indexes {
    (region_id, event_id, forecast_date) [unique]
  }

  checks {
    `probability BETWEEN 0 AND 100`
  }
}

Table alert {
  id uuid [pk, default: `gen_random_uuid()`]
  farm_id uuid [not null]
  event_id uuid [not null]
  threshold smallint [not null]

  indexes {
    (farm_id, event_id) [unique]
  }

  checks {
    `threshold BETWEEN 0 AND 100`
  }
}

Table notification {
  id uuid [pk, default: `gen_random_uuid()`]
  alert_id uuid [not null]
  forecast_date date [not null]
  probability smallint [not null, note: 'Snapshot del valor al momento de notificar']
  read_at timestamptz [null, note: 'Nulo significa no leida']
  created_at timestamptz [not null, default: `now()`]

  indexes {
    (alert_id, forecast_date) [unique]
  }
}

Ref: farm.user_id > users.id
Ref: farm.region_id > region.id [delete: restrict]
Ref: weather_forecast.region_id > region.id
Ref: weather_forecast.event_id > event.id
Ref: alert.farm_id > farm.id [delete: cascade]
Ref: alert.event_id > event.id
Ref: notification.alert_id > alert.id [delete: cascade]
```
