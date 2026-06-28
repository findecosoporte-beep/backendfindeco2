import { api } from '@/api/client'
import type { Pago } from '@/types/api'

/** Extrae el número de cuota del documento del pago (ej. «Cuota 3»). */
export function extractCuotaNumeroDocumento(documento: string | null | undefined): number | null {
  if (!documento) return null
  const match = documento.match(/cuota\s*(\d+)/i)
  if (!match) return null
  const cuota = Number.parseInt(match[1], 10)
  return Number.isFinite(cuota) ? cuota : null
}

/** Mapa número de cuota → pago (primer pago que coincida por documento). */
export function buildPagoPorCuotaNumero(pagos: Pago[]): Map<number, Pago> {
  const map = new Map<number, Pago>()
  for (const pago of pagos) {
    const n = extractCuotaNumeroDocumento(pago.documento)
    if (n != null && !map.has(n)) map.set(n, pago)
  }
  return map
}

/**
 * Igual que buildPagoPorCuotaNumero, pero asigna pagos restantes a cuotas libres
 * en orden cronológico (cuando el documento no trae «Cuota N»).
 */
export function buildPagoPorCuotaConFallback(
  cuotas: { numero_cuota: number }[],
  pagosOrdenados: Pago[],
): Map<number, Pago> {
  const map = buildPagoPorCuotaNumero(pagosOrdenados)
  const usados = new Set(Array.from(map.values()).map((p) => p.id_pago))
  const sinAsignar = pagosOrdenados.filter((p) => !usados.has(p.id_pago))
  const cuotasLibres = [...cuotas]
    .sort((a, b) => a.numero_cuota - b.numero_cuota)
    .filter((c) => !map.has(c.numero_cuota))
  for (let i = 0; i < sinAsignar.length && i < cuotasLibres.length; i++) {
    map.set(cuotasLibres[i]!.numero_cuota, sinAsignar[i]!)
  }
  return map
}

/** Abre el PDF de factura del pago en una pestaña nueva e invoca impresión. */
export async function abrirFacturaPago(idPago: number, ticketFormat: '58' | '80' = '58'): Promise<void> {
  const response = await api.get(`/pagos/${idPago}/factura-pdf/?ticket=${ticketFormat}`, {
    responseType: 'blob',
  })
  const pdfBlob = new Blob([response.data], { type: 'application/pdf' })
  const pdfUrl = URL.createObjectURL(pdfBlob)
  const pdfWindow = window.open(pdfUrl, '_blank')
  if (pdfWindow) {
    setTimeout(() => {
      pdfWindow.focus()
      pdfWindow.print()
    }, 700)
  }
  setTimeout(() => URL.revokeObjectURL(pdfUrl), 15000)
}
