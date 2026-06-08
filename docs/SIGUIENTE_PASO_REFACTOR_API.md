# Siguiente paso — Refactor priorizado de `api/` (sin tocar el front)

Documento operativo **después** del [PLAN_PRODUCCION.md](./PLAN_PRODUCCION.md).  
Objetivo: reducir riesgo de bugs y facilitar mantenimiento **sin cambiar URLs ni contratos JSON**.

---

## Antes de empezar (30 minutos)

```bash
cd Api1
python manage.py test api -v 2
```

- [ ] Todos los tests en verde → anota el resultado (ej. `Ran 21 tests … OK`).
- [ ] Crea rama: `refactor/api-modular-paso-a-paso`.
- [ ] Un PR por refactor (#1 … #5), merge solo con CI verde.

**Regla de oro:** ningún refactor cambia rutas (`/api/v1/...`), códigos HTTP ni forma de `{ success, error }`.

---

## Mapa de duplicación actual (por qué este orden)

| Lógica duplicada | `views.py` | `serializers.py` | Riesgo si cambias solo un archivo |
|------------------|------------|------------------|-----------------------------------|
| Número de cuota en `documento` | `_extract_cuota_numero_documento` | `PagoSerializer._extract_cuota_numero` | Cobro duplicado o no detectado |
| Tasa / periodos del préstamo | `_periodic_rate_from_nominal`, `_periods_from_months` | mismas funciones | Cálculo distinto simular vs guardar |
| Redondeo dinero | `_round_money` | (parcial vía Decimal) | Totales PDF ≠ API |

Por eso el **Paso 1** es unificar utilidades; el resto extrae dominio encima de esa base.

---

## Paso 1 — Módulo `api/core/` (utilidades compartidas)

**Prioridad:** máxima · **Esfuerzo:** 0,5–1 día · **Riesgo:** bajo

### Objetivo

Un solo lugar para dinero, cuotas y tasas; eliminar copias entre `views.py` y `serializers.py`.

### Archivos nuevos

```
api/core/
  __init__.py
  money.py          # round_money, CENTS
  cuotas.py         # extract_cuota_numero_from_documento(documento) -> int | None
  prestamo_calc.py  # periodic_rate_from_nominal, periods_from_months
  fechas.py         # add_months, calculate_fecha_vencimiento, calculate_fecha_cuota
```

### Cambios en existentes

- `views.py`: importar desde `api.core.*`; borrar funciones `_extract_cuota_*`, `_round_money`, `_periodic_rate_*`, `_periods_from_months` locales.
- `serializers.py`: importar lo mismo; borrar duplicados; `PagoSerializer` usa `extract_cuota_numero_from_documento` del core.

### Tests a añadir (`api/tests/test_core.py`)

| Test | Caso |
|------|------|
| `test_extract_cuota` | `"Cuota 3"` → `3`, `"cuota 12"` → `12`, `""` → `None` |
| `test_round_money` | `1.005` → `1.01` (HALF_UP) |
| `test_periods_semanal` | plazo 12 meses → 48 periodos |

### Criterios de aceptación

- [ ] `python manage.py test api` verde.
- [ ] `rg "_extract_cuota_numero_documento|_periodic_rate_from_nominal"` en `api/` solo en `core/` o tests.
- [ ] Front: simular préstamo + registrar cobro manual (smoke) sin cambios.

### PR sugerido

`título: refactor(api): centralizar utilidades en api.core`

---

## Paso 2 — Dominio cobros `api/pagos/`

**Prioridad:** alta · **Esfuerzo:** 1–1,5 días · **Riesgo:** medio (afecta dinero)

### Objetivo

Sacar reglas de **Pago** del serializer gordo: duplicados, sync estado préstamo, validación montos.

### Archivos nuevos

```
api/pagos/
  __init__.py
  services.py   # validate_pago, create_pago, update_pago, sync_prestamo_from_pago
  serializers.py # PagoSerializer (delgado)
  views.py      # PagoViewSet + acciones factura-pdf / hoja-semanal (o pdf en core)
```

### Qué mueve `services.py`

- `_validate_cuota_duplicate` → función de servicio.
- `_sync_prestamo_state` → `sync_prestamo_state_after_pago(pago)`.
- `create`/`update` del serializer llaman al servicio dentro de `@transaction.atomic` + `select_for_update`.

### Criterios de aceptación

- [ ] Tests existentes de pago duplicado y estado `pagado`/`mora` siguen verdes.
- [ ] Test nuevo: dos pagos misma cuota → segundo rechazado.
- [ ] `POST /api/v1/pagos/` sin cambio de payload.

### PR sugerido

`refactor(api): extraer lógica de pagos a api.pagos.services`

---

## Paso 3 — Dominio préstamos `api/prestamos/`

**Prioridad:** alta · **Esfuerzo:** 1,5–2 días · **Riesgo:** medio

### Objetivo

Aislar **simulación/cálculo**, alta de préstamo, plan de cuotas y reporte integración.

### Archivos nuevos

```
api/prestamos/
  __init__.py
  services.py      # simular_prestamo(...), generar_plan_cuotas(...), reporte_integracion(...)
  serializers.py   # PrestamoSerializer, PrestamoCuotaSerializer, SimulacionPrestamoSerializer
  views.py         # PrestamoViewSet, PrestamoCuotaViewSet, SimulacionPrestamoView
```

### Qué sale de `views.py` hoy

- Clase/vista de simulación (~líneas con `amortizacion`, `cuota_periodica`).
- `@action reporte-integracion`, `registrar-impresion-hoja-cobros`.

### Criterios de aceptación

- [ ] `POST /api/v1/prestamos/simular/` respuesta igual estructura que antes.
- [ ] `POST /api/v1/prestamos/` sigue generando cuotas automáticas.
- [ ] Tests `test_crear_prestamo_genera_plan_cuotas` y `test_simulacion_prestamo_*` verdes.

### PR sugerido

`refactor(api): módulo prestamos (simulación, plan, reporte)`

---

## Paso 4 — PDF y documentos en `api/core/pdf.py` + `api/clientes/`

**Prioridad:** media · **Esfuerzo:** 1 día · **Riesgo:** bajo–medio

### Objetivo

Sacar **ReportLab** de `views.py` (~100+ líneas de dibujo PDF) para que vistas solo devuelvan `HttpResponse`.

### Archivos

```
api/core/pdf.py           # build_pago_invoice_pdf(pago, ticket_format) -> bytes
api/clientes/
  views.py                # ClienteViewSet, ClienteDocumentoViewSet, finalizar_expediente
  serializers.py
```

### Criterios de aceptación

- [ ] `GET /api/v1/pagos/{id}/factura-pdf/` devuelve PDF válido (test existente verde).
- [ ] `views.py` global baja de ~870 a < 500 líneas tras pasos 1–4.

### PR sugerido

`refactor(api): extraer generación PDF y vistas de clientes`

---

## Paso 5 — URLs y catálogos `api/catalogos/` + `urls` finales

**Prioridad:** media · **Esfuerzo:** 0,5–1 día · **Riesgo:** bajo

### Objetivo

Cerrar modularización: zonas, carteras, usuarios, historial, `MeView`.

### Estructura final objetivo

```
api/
  core/
  clientes/
  prestamos/
  pagos/
  catalogos/     # Zona, Cartera, Usuario, HistorialPrestamo, MeView
  urls.py        # router + include por app
  models.py      # se queda (o split posterior opcional)
  permissions.py
  exceptions.py
  pagination.py
  admin.py
  tests/         # opcional: tests/test_pagos.py, etc.
```

### `api/urls.py` ejemplo

```python
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from api.prestamos.views import PrestamoViewSet, ...
from api.pagos.views import PagoViewSet
# ...

router = DefaultRouter()
router.register(r'prestamos', PrestamoViewSet, ...)
# ...

urlpatterns = [
    path('me/', MeView.as_view()),
    path('prestamos/simular/', SimulacionPrestamoView.as_view()),
    path('', include(router.urls)),
]
```

### Criterios de aceptación

- [ ] `api/views.py` eliminado o solo reexporta (deprecation temporal).
- [ ] OpenAPI `/api/v1/docs/` lista los mismos endpoints.
- [ ] Suite completa de tests verde.

### PR sugerido

`refactor(api): catalogos y urls modulares; eliminar views monolítico`

---

## Orden y calendario sugerido

| Semana | PR | Hito |
|--------|-----|------|
| 1 | Paso 1 | Core unificado, menos duplicación |
| 1–2 | Paso 2 | Cobros más seguros de mantener |
| 2 | Paso 3 | Préstamos/cálculo aislados |
| 3 | Paso 4 + 5 | PDF + estructura final |

En paralelo con **Fase 0–1 del plan de producción** (`.gitignore`, `settings/production.py`) si hay otra persona en el equipo.

---

## Checklist “listo para seguir con producción” (post-refactor)

- [ ] Pasos 1–5 completados y mergeados.
- [ ] `views.py` monolítico eliminado.
- [ ] Tests ≥ los actuales + `test_core.py`.
- [ ] Luego aplicar [PLAN_PRODUCCION.md](./PLAN_PRODUCCION.md) Fase 1 (settings prod).

---

## Qué NO hacer en estos 5 pasos

- Cambiar nombres de campos JSON expuestos al front.
- Mover `models.py` a múltiples apps Django (opcional, fase posterior).
- Reescribir autenticación o permisos desde cero.
- Añadir microservicios.

---

## Comando rápido de verificación (después de cada PR)

```bash
cd Api1
python manage.py check
python manage.py test api -v 2
```

---

## Siguiente acción hoy (recomendada)

**Empezar solo el Paso 1** (`api/core/`). Es el que más reduce riesgo de inconsistencia entre simulación y cobro, con el menor cambio visible para usuarios.

Si quieres implementación asistida en el repo, pide: *“Implementa el Paso 1 del SIGUIENTE_PASO_REFACTOR_API”*.

---

*Relacionado: [PLAN_PRODUCCION.md](./PLAN_PRODUCCION.md) · App Django: `api/` · Tests: `api/tests.py`*
