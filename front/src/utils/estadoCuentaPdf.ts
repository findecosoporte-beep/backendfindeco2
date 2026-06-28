import { api } from '@/api/client'
import { abrirWhatsAppConMensaje, telefonoParaWhatsApp } from '@/utils/whatsappCliente'

export async function fetchEstadoCuentaPdfBlob(idPrestamo: number): Promise<Blob> {
  const response = await api.get(`/prestamos/${idPrestamo}/estado-cuenta-pdf/`, {
    responseType: 'blob',
  })
  return new Blob([response.data], { type: 'application/pdf' })
}

function mensajeCompartirEstadoCuenta(nombreCliente: string, numeroPrestamo?: string | null): string {
  const ref = numeroPrestamo ? ` del préstamo ${numeroPrestamo}` : ''
  return [
    'FINDECO — Estado de cuenta',
    '',
    `Estimado/a ${nombreCliente}, adjunto su estado de cuenta${ref}.`,
    '',
    'Gracias por su preferencia.',
  ].join('\n')
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

export function descargarEstadoCuentaPdf(blob: Blob, numeroPrestamo?: string | null) {
  const slug = (numeroPrestamo || 'findeco').replace(/\s+/g, '-')
  downloadBlob(blob, `estado-cuenta-${slug}.pdf`)
}

export async function compartirEstadoCuentaPdf(params: {
  telefono: string
  nombreCliente: string
  numeroPrestamo?: string | null
  pdfBlob: Blob
}): Promise<'shared' | 'whatsapp' | 'failed'> {
  const mensaje = mensajeCompartirEstadoCuenta(params.nombreCliente, params.numeroPrestamo)
  const file = new File([params.pdfBlob], 'estado-cuenta-findeco.pdf', { type: 'application/pdf' })

  if (typeof navigator.share === 'function') {
    try {
      const payload: ShareData = {
        files: [file],
        text: mensaje,
        title: 'Estado de cuenta FINDECO',
      }
      if (!navigator.canShare || navigator.canShare(payload)) {
        await navigator.share(payload)
        return 'shared'
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return 'shared'
    }
  }

  if (!telefonoParaWhatsApp(params.telefono)) return 'failed'
  const ok = abrirWhatsAppConMensaje(
    params.telefono,
    `${mensaje}\n\n(Adjunte el PDF descargado en este chat.)`,
  )
  if (!ok) return 'failed'
  descargarEstadoCuentaPdf(params.pdfBlob, params.numeroPrestamo)
  return 'whatsapp'
}
