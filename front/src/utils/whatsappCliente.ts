/** Utilidades para enviar resúmenes al WhatsApp del cliente (wa.me). */

export const PREFIJO_WHATSAPP_HN = '504'

export function telefonoParaWhatsApp(
  telefono: string,
  prefijoPais: string = PREFIJO_WHATSAPP_HN,
): string | null {
  let digits = telefono.replace(/\D/g, '')
  if (!digits) return null
  if (digits.startsWith('00')) digits = digits.slice(2)
  if (digits.length === 8) return `${prefijoPais}${digits}`
  if (digits.length >= 10) return digits
  return null
}

export function abrirWhatsAppConMensaje(telefono: string, mensaje: string): boolean {
  const destino = telefonoParaWhatsApp(telefono)
  if (!destino) return false
  const url = `https://wa.me/${destino}?text=${encodeURIComponent(mensaje)}`
  window.open(url, '_blank', 'noopener,noreferrer')
  return true
}

export interface ResumenWhatsAppCobros {
  nombre: string
  dni: string
  prestamoLabel?: string | null
  cuotaNumero?: number
  cuotaMonto?: string
  cuotaFecha?: string
  saldoActual?: string
  cuotasAtrasadas?: string
  notaCuota?: string
}

export function mensajeConsultaClienteCobros(params: ResumenWhatsAppCobros): string {
  const lineas = [
    'FINDECO — Información de su préstamo',
    '',
    `Cliente: ${params.nombre}`,
    `DNI: ${params.dni}`,
  ]
  if (params.prestamoLabel) lineas.push(`Préstamo: ${params.prestamoLabel}`)
  if (params.cuotaNumero != null && params.cuotaMonto) {
    lineas.push('', `Cuota #${params.cuotaNumero} pendiente: ${params.cuotaMonto}`)
    if (params.cuotaFecha) lineas.push(`Fecha programada: ${params.cuotaFecha}`)
  }
  if (params.saldoActual) lineas.push(`Saldo actual: ${params.saldoActual}`)
  if (params.cuotasAtrasadas) lineas.push(params.cuotasAtrasadas)
  if (params.notaCuota) lineas.push('', params.notaCuota)
  lineas.push('', 'Gracias por su preferencia.')
  return lineas.join('\n')
}

export interface CuotaResumenWhatsApp {
  numero: number
  fecha: string
  total: string
}

export interface ResumenWhatsAppEstadoCuenta {
  nombre: string
  dni: string
  numeroPrestamo: string
  cartera: string
  pendientes: CuotaResumenWhatsApp[]
  totalPendientes: number
  cuotasPagadas: number
  totalAbonado: string
}

export function mensajeEstadoCuentaFindeco(params: ResumenWhatsAppEstadoCuenta): string {
  const lineas = [
    'FINDECO — Estado de cuenta',
    '',
    `Cliente: ${params.nombre}`,
    `DNI: ${params.dni}`,
  ]
  if (params.numeroPrestamo) lineas.push(`Préstamo: ${params.numeroPrestamo}`)
  if (params.cartera) lineas.push(`Cartera: ${params.cartera}`)
  lineas.push('', `Cuotas pagadas: ${params.cuotasPagadas}`)
  lineas.push(`Total abonado: ${params.totalAbonado}`)
  if (params.totalPendientes > 0) {
    lineas.push('', `Cuotas pendientes: ${params.totalPendientes}`)
    for (const c of params.pendientes) {
      lineas.push(`  • Cuota #${c.numero} — ${c.total} — vence ${c.fecha}`)
    }
    if (params.totalPendientes > params.pendientes.length) {
      lineas.push(`  … y ${params.totalPendientes - params.pendientes.length} más`)
    }
  } else {
    lineas.push('', 'No tiene cuotas pendientes en este préstamo.')
  }
  lineas.push('', 'Gracias por su preferencia.')
  return lineas.join('\n')
}

export interface ResumenWhatsAppEstadoCuentaModal {
  nombre: string
  dni: string
  totalPagos: number
  totalCapital: string
  totalInteres: string
  totalMora: string
  estadoPrestamo: string
  diasMora: number
}

export function mensajeEstadoCuentaModal(params: ResumenWhatsAppEstadoCuentaModal): string {
  return [
    'FINDECO — Estado de cuenta',
    '',
    `Cliente: ${params.nombre}`,
    `DNI: ${params.dni}`,
    '',
    `Cobros registrados: ${params.totalPagos}`,
    `Capital pagado: ${params.totalCapital}`,
    `Interés pagado: ${params.totalInteres}`,
    `Mora pagada: ${params.totalMora}`,
    `Estado del préstamo: ${params.estadoPrestamo || 'N/A'}`,
    `Días en mora: ${params.diasMora}`,
    '',
    'Gracias por su preferencia.',
  ].join('\n')
}
