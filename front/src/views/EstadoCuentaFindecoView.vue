<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'

import { api } from '@/api/client'
import { getApiErrorMessage } from '@/api/errors'
import { formatDate, formatMoney } from '@/utils/format'
import { abrirFacturaPago, buildPagoPorCuotaConFallback } from '@/utils/facturaPago'
import EstadoCuentaPdfDialog from '@/components/EstadoCuentaPdfDialog.vue'
import type { Cartera, Cliente, Paginated, Pago, Prestamo, PrestamoCuotaRow } from '@/types/api'

const toast = useToast()

const loading = ref(false)
const error = ref('')
const info = ref('')

/** Valores de los campos de búsqueda y resultado. */
const campos = ref({
  n: '',
  cartera: '',
  cliente: '',
  identidad: '',
  telefono: '',
})

const carteraNombrePorZonaId = ref<Record<number, string>>({})

const idPrestamoActivo = ref<number | null>(null)
const idClienteActivo = ref<number | null>(null)
const cuotasPlan = ref<PrestamoCuotaRow[]>([])
const abonos = ref<Pago[]>([])
const historialPrestamos = ref<Prestamo[]>([])
const loadingPlan = ref(false)
const loadingHistorialPrestamos = ref(false)
const facturaAbriendoId = ref<number | null>(null)
const estadoCuentaPdfVisible = ref(false)

const ETIQUETAS_ESTADO_PRESTAMO: Record<string, string> = {
  pendiente_aprobacion: 'Pendiente aprobación',
  activo: 'Activo',
  pagado: 'Pagado',
  mora: 'Mora',
  cancelado: 'Cancelado',
}

function etiquetaEstadoPrestamo(estado: string): string {
  return ETIQUETAS_ESTADO_PRESTAMO[estado] ?? estado
}

function severidadEstadoPrestamo(
  estado: string,
): 'success' | 'warn' | 'danger' | 'secondary' | 'info' | 'contrast' {
  if (estado === 'activo') return 'success'
  if (estado === 'pagado') return 'info'
  if (estado === 'mora') return 'danger'
  if (estado === 'cancelado') return 'secondary'
  if (estado === 'pendiente_aprobacion') return 'warn'
  return 'secondary'
}

const historialPrestamosOrdenado = computed(() =>
  [...historialPrestamos.value].sort((a, b) => {
    const ta = new Date(a.fecha_entrega).getTime()
    const tb = new Date(b.fecha_entrega).getTime()
    if (ta !== tb) return tb - ta
    return b.id_prestamo - a.id_prestamo
  }),
)

interface FilaCuotaEstado {
  numero_cuota: number
  fecha_programada: string
  total_programado: string | number
  saldo_capital_programado: string | number
  estado: 'pendiente' | 'pagada'
  id_pago: number | null
  fecha_pago: string | null
  documento: string | null
}

async function verFacturaPago(idPago: number) {
  facturaAbriendoId.value = idPago
  try {
    await abrirFacturaPago(idPago)
  } catch (e) {
    toast.add({
      severity: 'error',
      summary: 'Factura',
      detail: getApiErrorMessage(e),
      life: 5000,
    })
  } finally {
    facturaAbriendoId.value = null
  }
}

/** Abonos en orden cronológico para alinear N con la secuencia de pagos. */
const abonosOrdenados = computed(() =>
  [...abonos.value].sort((a, b) => {
    const ta = new Date(a.fecha_pago).getTime()
    const tb = new Date(b.fecha_pago).getTime()
    if (ta !== tb) return ta - tb
    return a.id_pago - b.id_pago
  }),
)

const pagoPorCuota = computed(() => buildPagoPorCuotaConFallback(cuotasPlan.value, abonosOrdenados.value))

const filasCuotasEstado = computed((): FilaCuotaEstado[] =>
  [...cuotasPlan.value]
    .sort((a, b) => a.numero_cuota - b.numero_cuota)
    .map((cuota) => {
      const pago = pagoPorCuota.value.get(cuota.numero_cuota)
      return {
        numero_cuota: cuota.numero_cuota,
        fecha_programada: cuota.fecha_programada,
        total_programado: cuota.total_programado,
        saldo_capital_programado: cuota.saldo_capital_programado,
        estado: pago ? 'pagada' : 'pendiente',
        id_pago: pago?.id_pago ?? null,
        fecha_pago: pago?.fecha_pago ?? null,
        documento: pago?.documento ?? null,
      }
    }),
)

const cuotasPendientes = computed(() => filasCuotasEstado.value.filter((f) => f.estado === 'pendiente'))
const cuotasPagadas = computed(() => filasCuotasEstado.value.filter((f) => f.estado === 'pagada'))

const totalAbonado = computed(() =>
  abonosOrdenados.value.reduce(
    (sum, p) => sum + (Number(p.capital) || 0) + (Number(p.interes) || 0) + (Number(p.mora) || 0),
    0,
  ),
)

function abrirEstadoCuentaPdf() {
  if (idPrestamoActivo.value == null) return
  estadoCuentaPdfVisible.value = true
}

async function fetchAllPages<T>(initialPath: string): Promise<T[]> {
  const items: T[] = []
  let nextUrl: string | null = initialPath
  while (nextUrl) {
    const response = await api.get<Paginated<T>>(nextUrl)
    const pageData = response.data as Paginated<T>
    items.push(...pageData.results)
    nextUrl = pageData.next
  }
  return items
}

async function cargarCarterasPorZona() {
  try {
    const carteras = await fetchAllPages<Cartera>('/carteras/?page_size=100')
    const map: Record<number, string> = {}
    for (const c of carteras) {
      const zid = c.id_zona
      if (zid != null && zid > 0) map[zid] = c.nombre.trim()
    }
    carteraNombrePorZonaId.value = map
  } catch {
    carteraNombrePorZonaId.value = {}
  }
}

function textoCarteraDesdePrestamo(p: Prestamo): string {
  const idZ = p.id_zona ?? p.zona?.id_zona
  if (idZ != null && idZ > 0) {
    const nom = carteraNombrePorZonaId.value[idZ]
    if (nom) return nom
    return p.zona?.nombre?.trim() || ''
  }
  return p.zona?.nombre?.trim() || ''
}

async function cargarHistorialPrestamos(idCliente: number) {
  loadingHistorialPrestamos.value = true
  historialPrestamos.value = []
  try {
    historialPrestamos.value = await fetchAllPages<Prestamo>(
      `/prestamos/?id_cliente=${idCliente}&page_size=100&ordering=-fecha_entrega,-id_prestamo`,
    )
  } catch {
    historialPrestamos.value = []
  } finally {
    loadingHistorialPrestamos.value = false
  }
}

async function seleccionarPrestamoHistorial(p: Prestamo) {
  if (p.id_prestamo === idPrestamoActivo.value) return
  idPrestamoActivo.value = p.id_prestamo
  campos.value.n = p.numero_prestamo?.trim() ?? campos.value.n
  const cartera = textoCarteraDesdePrestamo(p)
  if (cartera) campos.value.cartera = cartera
  await cargarPlanYPagos(p.id_prestamo)
}

async function cargarPlanYPagos(idPrestamo: number) {
  loadingPlan.value = true
  cuotasPlan.value = []
  abonos.value = []
  try {
    const [cuotas, pagosRows] = await Promise.all([
      fetchAllPages<PrestamoCuotaRow>(
        `/prestamo-cuotas/?id_prestamo=${idPrestamo}&page_size=100&ordering=numero_cuota`,
      ),
      fetchAllPages<Pago>(`/pagos/?id_prestamo=${idPrestamo}&page_size=100&ordering=fecha_pago,id_pago`),
    ])
    cuotasPlan.value = cuotas
    abonos.value = pagosRows
  } catch {
    cuotasPlan.value = []
    abonos.value = []
  } finally {
    loadingPlan.value = false
  }
}

async function cargarCliente(idCliente: number): Promise<Cliente> {
  const { data } = await api.get<Cliente>(`/clientes/${idCliente}/`)
  return data
}

function aplicarPrestamoYCliente(p: Prestamo, c: Cliente, avisoVarios?: string) {
  campos.value = {
    n: p.numero_prestamo?.trim() ?? '',
    cartera: textoCarteraDesdePrestamo(p),
    cliente: c.nombre?.trim() ?? '',
    identidad: c.dni?.trim() ?? '',
    telefono: (c.telefono ?? '').trim(),
  }
  info.value = avisoVarios ?? ''
  idPrestamoActivo.value = p.id_prestamo
  idClienteActivo.value = p.id_cliente
  void cargarPlanYPagos(p.id_prestamo)
  void cargarHistorialPrestamos(p.id_cliente)
}

async function primerPrestamoDesdeListado(params: URLSearchParams): Promise<Prestamo | null> {
  params.set('page_size', '10')
  params.set('ordering', '-id_prestamo')
  const { data } = await api.get<Paginated<Prestamo>>(`/prestamos/?${params.toString()}`)
  if (!data.results.length) return null
  return data.results[0]!
}

function requiereValor(raw: string, etiqueta: string): string | null {
  const v = raw.trim()
  if (!v) {
    error.value = `Ingresa un valor en ${etiqueta} para buscar.`
    return null
  }
  return v
}

async function buscarPorNumeroPrestamo() {
  const v = requiereValor(campos.value.n, 'N')
  if (v == null) return
  const params = new URLSearchParams({ numero_prestamo: v })
  const p = await primerPrestamoDesdeListado(params)
  if (!p) {
    error.value = 'No se encontró préstamo con ese número.'
    return
  }
  const c = await cargarCliente(p.id_cliente)
  aplicarPrestamoYCliente(p, c)
}

async function buscarPorCartera() {
  const v = requiereValor(campos.value.cartera, 'CARTERA')
  if (v == null) return
  const { data } = await api.get<Paginated<Cartera>>(
    `/carteras/?search=${encodeURIComponent(v)}&page_size=20`,
  )
  const conZona = data.results.filter((c) => c.id_zona != null && c.id_zona > 0)
  if (!conZona.length) {
    error.value = 'No se encontró cartera con ese nombre (o sin zona asignada).'
    return
  }
  const idZona = conZona[0]!.id_zona!
  const params = new URLSearchParams({ id_zona: String(idZona) })
  const p = await primerPrestamoDesdeListado(params)
  if (!p) {
    error.value = 'No hay préstamos en la zona de esa cartera.'
    return
  }
  const c = await cargarCliente(p.id_cliente)
  const aviso =
    data.count > 1
      ? 'Varias carteras coinciden; se usó la primera con zona asignada y el préstamo más reciente de esa zona.'
      : data.results.length > 1
        ? 'Varios préstamos en la zona; se muestra el más reciente.'
        : ''
  aplicarPrestamoYCliente(p, c, aviso || undefined)
}

async function buscarPorCliente() {
  const v = requiereValor(campos.value.cliente, 'CLIENTE')
  if (v == null) return
  const { data } = await api.get<Paginated<Cliente>>(
    `/clientes/?search=${encodeURIComponent(v)}&page_size=30`,
  )
  if (!data.results.length) {
    error.value = 'No se encontró cliente con ese nombre.'
    return
  }
  const exact = data.results.find((c) => c.nombre.trim().toLowerCase() === v.toLowerCase())
  const cliente = exact ?? data.results[0]!
  const params = new URLSearchParams({ id_cliente: String(cliente.id_cliente) })
  const p = await primerPrestamoDesdeListado(params)
  if (!p) {
    error.value = 'El cliente no tiene préstamos registrados.'
    return
  }
  const c = await cargarCliente(p.id_cliente)
  const aviso =
    data.results.length > 1 && !exact
      ? 'Varios clientes coinciden; se usó el primero y su préstamo más reciente.'
      : ''
  aplicarPrestamoYCliente(p, c, aviso || undefined)
}

async function buscarPorIdentidad() {
  const v = requiereValor(campos.value.identidad, 'IDENTIDAD')
  if (v == null) return
  const { data } = await api.get<Paginated<Cliente>>(`/clientes/?dni=${encodeURIComponent(v)}&page_size=5`)
  if (!data.results.length) {
    error.value = 'No se encontró cliente con esa identidad.'
    return
  }
  const cliente = data.results[0]!
  const params = new URLSearchParams({ id_cliente: String(cliente.id_cliente) })
  const p = await primerPrestamoDesdeListado(params)
  if (!p) {
    error.value = 'El cliente no tiene préstamos registrados.'
    return
  }
  const c = await cargarCliente(p.id_cliente)
  aplicarPrestamoYCliente(p, c)
}

async function buscarPorTelefono() {
  const v = requiereValor(campos.value.telefono, 'TELEFONO')
  if (v == null) return
  const norm = v.replace(/\s+/g, '')
  const { data } = await api.get<Paginated<Cliente>>(
    `/clientes/?search=${encodeURIComponent(v)}&page_size=40`,
  )
  const exact = data.results.find((c) => (c.telefono ?? '').replace(/\s+/g, '') === norm)
  const cliente = exact ?? data.results[0]
  if (!cliente) {
    error.value = 'No se encontró cliente con ese teléfono.'
    return
  }
  const params = new URLSearchParams({ id_cliente: String(cliente.id_cliente) })
  const p = await primerPrestamoDesdeListado(params)
  if (!p) {
    error.value = 'El cliente no tiene préstamos registrados.'
    return
  }
  const c = await cargarCliente(p.id_cliente)
  const aviso =
    data.results.length > 1 && !exact
      ? 'Varios clientes coinciden con la búsqueda; se usó el primero con coincidencia exacta de teléfono si existía.'
      : ''
  aplicarPrestamoYCliente(p, c, aviso || undefined)
}

type CampoBusqueda =
  | 'n'
  | 'cartera'
  | 'cliente'
  | 'identidad'
  | 'telefono'

/** Si hay varios campos con valor, solo se usa el primero en este orden. */
function primerCampoConValor(): CampoBusqueda | null {
  const c = campos.value
  if (c.n.trim()) return 'n'
  if (c.cartera.trim()) return 'cartera'
  if (c.cliente.trim()) return 'cliente'
  if (c.identidad.trim()) return 'identidad'
  if (c.telefono.trim()) return 'telefono'
  return null
}

async function ejecutarBusquedaUnica() {
  const campo = primerCampoConValor()
  if (campo == null) {
    error.value =
      'Escribe al menos un dato en un campo. Si rellenas varios, se usa solo el primero en este orden: N → Cartera → Cliente → Identidad → Teléfono.'
    return
  }
  await buscarPorCampo(campo)
}

async function buscarPorCampo(campo: CampoBusqueda) {
  error.value = ''
  info.value = ''
  idPrestamoActivo.value = null
  idClienteActivo.value = null
  cuotasPlan.value = []
  abonos.value = []
  historialPrestamos.value = []
  loading.value = true
  try {
    if (campo === 'n') await buscarPorNumeroPrestamo()
    else if (campo === 'cartera') await buscarPorCartera()
    else if (campo === 'cliente') await buscarPorCliente()
    else if (campo === 'identidad') await buscarPorIdentidad()
    else if (campo === 'telefono') await buscarPorTelefono()
  } catch (e) {
    error.value = getApiErrorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void cargarCarterasPorZona()
})
</script>

<template>
  <div class="page-twelve-col">
    <header class="titulo-marca span-full" aria-label="Estado de cuenta FINDECO">
      <p class="titulo-marca-eyebrow">Estado de cuenta</p>
      <div class="titulo-marca-caja">
        <span class="titulo-marca-texto">FINDECO</span>
      </div>
    </header>

    <h1 class="title span-full">Estado de cuenta FINDECO</h1>

    <Message v-if="error" class="span-full" severity="error" :closable="false">{{ error }}</Message>
    <Message v-if="info" class="span-full" severity="info" :closable="true" @close="info = ''">{{ info }}</Message>

    <div class="layout-apilado span-full">
      <div class="bloque-buscador">
        <form class="panel-busqueda" aria-label="Consulta por campo" @submit.prevent="ejecutarBusquedaUnica">
          <div class="fila-busqueda">
            <span class="ficha-label">N:</span>
            <InputText v-model="campos.n" class="fila-input" placeholder="Número de préstamo" :disabled="loading" />
          </div>
          <div class="fila-busqueda">
            <span class="ficha-label">CARTERA:</span>
            <InputText v-model="campos.cartera" class="fila-input" placeholder="Nombre de cartera" :disabled="loading" />
          </div>
          <div class="fila-busqueda">
            <span class="ficha-label">CLIENTE:</span>
            <InputText v-model="campos.cliente" class="fila-input" placeholder="Nombre del cliente" :disabled="loading" />
          </div>
          <div class="fila-busqueda">
            <span class="ficha-label">IDENTIDAD:</span>
            <InputText v-model="campos.identidad" class="fila-input" placeholder="DNI / identidad" :disabled="loading" />
          </div>
          <div class="fila-busqueda">
            <span class="ficha-label">TELEFONO:</span>
            <InputText v-model="campos.telefono" class="fila-input" placeholder="Teléfono" :disabled="loading" />
          </div>
          <div class="panel-busqueda-footer">
            <Button type="submit" label="Buscar" icon="pi pi-search" :loading="loading" :disabled="loading" />
          </div>
        </form>
      </div>

      <div class="bloque-resultados">
        <template v-if="idPrestamoActivo != null">
          <div class="cliente-whatsapp-bar">
            <div class="cliente-whatsapp-datos">
              <strong>{{ campos.cliente || 'Cliente' }}</strong>
              <span v-if="campos.identidad"> · DNI {{ campos.identidad }}</span>
              <span v-if="campos.telefono"> · {{ campos.telefono }}</span>
              <span v-else class="cliente-sin-tel"> · Sin teléfono</span>
            </div>
            <Button
              label="Estado de cuenta PDF"
              icon="pi pi-file-pdf"
              type="button"
              severity="success"
              outlined
              size="small"
              :disabled="loadingPlan"
              @click="abrirEstadoCuentaPdf"
            />
          </div>
          <div class="seccion-tablas">
            <h2 class="subtitulo">Cuotas pendientes</h2>
            <p v-if="!loadingPlan && !cuotasPendientes.length" class="tabla-vacia">
              No hay cuotas pendientes en el plan de pago.
            </p>
            <DataTable
              v-else
              :value="cuotasPendientes"
              data-key="numero_cuota"
              class="tabla-plan"
              size="small"
              :loading="loadingPlan"
            >
              <Column field="numero_cuota" header="N" />
              <Column header="FECHA">
                <template #body="{ data }: { data: FilaCuotaEstado }">
                  {{ formatDate(data.fecha_programada) }}
                </template>
              </Column>
              <Column header="CUOTA">
                <template #body="{ data }: { data: FilaCuotaEstado }">
                  {{ formatMoney(data.total_programado) }}
                </template>
              </Column>
              <Column header="SALDO">
                <template #body="{ data }: { data: FilaCuotaEstado }">
                  {{ formatMoney(data.saldo_capital_programado) }}
                </template>
              </Column>
              <Column header="ESTADO">
                <template #body>
                  <span class="estado-cuota-texto">Pendiente</span>
                </template>
              </Column>
            </DataTable>

            <h2 class="subtitulo subtitulo--segundo">Cuotas pagadas</h2>
            <p v-if="!loadingPlan && !cuotasPagadas.length" class="tabla-vacia">
              Aún no hay cuotas pagadas registradas en este préstamo.
            </p>
            <DataTable
              v-else
              :value="cuotasPagadas"
              data-key="numero_cuota"
              class="tabla-plan"
              size="small"
              :loading="loadingPlan"
            >
              <Column field="numero_cuota" header="N" />
              <Column header="FECHA PAGO">
                <template #body="{ data }: { data: FilaCuotaEstado }">
                  {{ data.fecha_pago ? formatDate(data.fecha_pago) : '—' }}
                </template>
              </Column>
              <Column header="CUOTA">
                <template #body="{ data }: { data: FilaCuotaEstado }">
                  {{ formatMoney(data.total_programado) }}
                </template>
              </Column>
              <Column header="DOCUMENTO">
                <template #body="{ data }: { data: FilaCuotaEstado }">
                  {{ data.documento || `Cuota ${data.numero_cuota}` }}
                </template>
              </Column>
              <Column header="FACTURA">
                <template #body="{ data }: { data: FilaCuotaEstado }">
                  <Button
                    v-if="data.id_pago"
                    icon="pi pi-file-pdf"
                    label="Ver factura"
                    size="small"
                    severity="secondary"
                    outlined
                    :loading="facturaAbriendoId === data.id_pago"
                    :disabled="facturaAbriendoId != null && facturaAbriendoId !== data.id_pago"
                    @click="verFacturaPago(data.id_pago)"
                  />
                  <span v-else class="texto-muted">—</span>
                </template>
              </Column>
            </DataTable>

            <h2 class="subtitulo subtitulo--segundo">Historial de préstamos</h2>
            <p v-if="!loadingHistorialPrestamos && !historialPrestamosOrdenado.length" class="tabla-vacia">
              No hay préstamos registrados para este cliente.
            </p>
            <DataTable
              v-else
              :value="historialPrestamosOrdenado"
              data-key="id_prestamo"
              class="tabla-abonos tabla-ec-fin tabla-historial-prestamos"
              size="small"
              striped-rows
              :loading="loadingHistorialPrestamos"
              :row-class="(data: Prestamo) => (data.id_prestamo === idPrestamoActivo ? 'fila-prestamo-activo' : '')"
            >
              <Column header="Nº" :style="{ width: '14%' }">
                <template #body="{ data }: { data: Prestamo }">
                  {{ data.numero_prestamo || data.id_prestamo }}
                </template>
              </Column>
              <Column header="FECHA ENTREGA" :style="{ width: '14%' }">
                <template #body="{ data }: { data: Prestamo }">
                  {{ formatDate(data.fecha_entrega) }}
                </template>
              </Column>
              <Column header="MONTO" :style="{ width: '14%' }">
                <template #body="{ data }: { data: Prestamo }">
                  {{ formatMoney(data.monto) }}
                </template>
              </Column>
              <Column header="PLAZO" :style="{ width: '10%' }">
                <template #body="{ data }: { data: Prestamo }">
                  {{ data.plazo }}
                </template>
              </Column>
              <Column header="CARTERA" :style="{ width: '18%' }">
                <template #body="{ data }: { data: Prestamo }">
                  {{ textoCarteraDesdePrestamo(data) || '—' }}
                </template>
              </Column>
              <Column header="ESTADO" :style="{ width: '16%' }">
                <template #body="{ data }: { data: Prestamo }">
                  <Tag :severity="severidadEstadoPrestamo(data.estado)" :value="etiquetaEstadoPrestamo(data.estado)" />
                </template>
              </Column>
              <Column header="ACCIÓN" :style="{ width: '14%' }">
                <template #body="{ data }: { data: Prestamo }">
                  <Tag v-if="data.id_prestamo === idPrestamoActivo" severity="info" value="Actual" />
                  <Button
                    v-else
                    label="Ver"
                    size="small"
                    severity="secondary"
                    outlined
                    @click="seleccionarPrestamoHistorial(data)"
                  />
                </template>
              </Column>
            </DataTable>
          </div>
        </template>
        <div v-else class="placeholder-resultados" aria-hidden="true">
          <p>Las cuotas pendientes, pagadas y el historial de préstamos aparecerán aquí después de localizar un préstamo.</p>
        </div>
      </div>
    </div>

    <EstadoCuentaPdfDialog
      v-model:visible="estadoCuentaPdfVisible"
      :prestamo-id="idPrestamoActivo"
      :telefono="campos.telefono"
      :nombre-cliente="campos.cliente || 'Cliente'"
      :numero-prestamo="campos.n || null"
    />
  </div>
</template>

<style scoped>
.page-twelve-col {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 0.65rem 1rem;
  align-content: start;
  max-width: 100%;
}

.span-full {
  grid-column: 1 / -1;
}

.titulo-marca {
  margin: 0 0 0.25rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.65rem;
  text-align: center;
}

.titulo-marca-eyebrow {
  margin: 0;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  color: #64748b;
}

.titulo-marca-caja {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: min(100%, 16rem);
  padding: 0.85rem 2.25rem;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 2px rgb(15 23 42 / 4%);
}

.titulo-marca-texto {
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: clamp(1.65rem, 5vw, 2.35rem);
  font-weight: 800;
  line-height: 1;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: #0a0a0a;
}

.title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  text-align: center;
}

.layout-apilado {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
  width: 100%;
}

.bloque-buscador,
.bloque-resultados {
  width: 100%;
  min-width: 0;
}

.bloque-resultados {
  margin-top: 0.15rem;
}

.cliente-whatsapp-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1rem;
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #f8fafc;
}

.cliente-whatsapp-datos {
  font-size: 0.9rem;
  color: #0f172a;
}

.cliente-sin-tel {
  color: #64748b;
}

.placeholder-resultados {
  margin: 0;
  padding: 1.25rem 1rem;
  border: 1px dashed #c9d4ec;
  border-radius: 4px;
  background: #f8fafc;
  color: #64748b;
  font-size: 0.9rem;
  line-height: 1.45;
  text-align: center;
}

.placeholder-resultados p {
  margin: 0;
}

.panel-busqueda {
  width: 100%;
  max-width: none;
  margin: 0;
  background: #fff;
  border: 1px solid #cbd5e1;
  border-radius: 2px;
  overflow: hidden;
}

.fila-busqueda {
  display: grid;
  grid-template-columns: minmax(8rem, 12rem) minmax(0, 1fr);
  align-items: center;
  gap: 0.5rem 0.85rem;
  padding: 0.55rem 0.9rem;
  border-bottom: 1px solid #cbd5e1;
}

.panel-busqueda .fila-busqueda:last-of-type {
  border-bottom: none;
}

.panel-busqueda-footer {
  display: flex;
  justify-content: flex-end;
  padding: 0.75rem 0.9rem 0.85rem;
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
}

.ficha-label {
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #0f172a;
  text-transform: uppercase;
  font-size: 0.82rem;
}

.fila-input {
  width: 100%;
  min-width: 0;
}

.seccion-tablas {
  margin-top: 0;
  width: 100%;
}

.tabla-vacia {
  margin: 0 0 0.75rem;
  padding: 0.75rem 1rem;
  border: 1px dashed #cbd5e1;
  border-radius: 4px;
  background: #f8fafc;
  color: #64748b;
  font-size: 0.88rem;
  text-align: center;
}

.texto-muted {
  color: #94a3b8;
  font-size: 0.85rem;
}

.subtitulo {
  margin: 0 0 0.5rem;
  font-size: 1.05rem;
  font-weight: 600;
  color: #1e293b;
  text-align: center;
}

.subtitulo--segundo {
  margin-top: 1.25rem;
}

.tabla-plan {
  width: 100%;
  display: block;
}

.tabla-plan :deep(.p-datatable) {
  width: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.tabla-plan :deep(.p-datatable-table-container),
.tabla-plan :deep(.p-datatable-table) {
  width: 100%;
}

.tabla-plan :deep(.p-datatable-table) {
  table-layout: fixed;
}

.tabla-plan :deep(.p-datatable-thead > tr > th) {
  background: #fff;
  color: #0f172a;
  border-color: #e2e8f0;
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.78rem;
  text-align: center;
  padding: 0.55rem 0.65rem;
}

.tabla-plan :deep(.p-datatable-tbody > tr > td) {
  background: #fff;
  color: #334155;
  border-color: #e2e8f0;
  text-align: center;
  padding: 0.5rem 0.65rem;
  font-size: 0.88rem;
}

.tabla-plan :deep(.p-datatable-tbody > tr:hover > td) {
  background: #fff;
}

.tabla-plan :deep(.p-datatable-tbody > tr.p-row-odd > td),
.tabla-plan :deep(.p-datatable-tbody > tr.p-row-even > td) {
  background: #fff;
}

.estado-cuota-texto {
  color: #334155;
  font-size: 0.88rem;
}

.tabla-abonos {
  width: 100%;
}

.tabla-ec-fin :deep(.p-datatable-thead > tr > th) {
  text-transform: uppercase;
  font-weight: 700;
  color: #0f172a;
  text-align: center;
}

.tabla-ec-fin :deep(.p-datatable-tbody > tr > td) {
  text-align: center;
}

.tabla-historial-prestamos :deep(.p-datatable-tbody > tr.fila-prestamo-activo > td) {
  background: #eff6ff;
}
</style>
