<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'

import { getApiErrorMessage } from '@/api/errors'
import {
  compartirEstadoCuentaPdf,
  descargarEstadoCuentaPdf,
  fetchEstadoCuentaPdfBlob,
} from '@/utils/estadoCuentaPdf'

const props = defineProps<{
  visible: boolean
  prestamoId: number | null
  telefono?: string | null
  nombreCliente?: string
  numeroPrestamo?: string | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const toast = useToast()
const loading = ref(false)
const sharing = ref(false)
const error = ref('')
const pdfUrl = ref<string | null>(null)
let pdfBlob: Blob | null = null

watch(
  () => [props.visible, props.prestamoId] as const,
  async ([visible, prestamoId]) => {
    if (!visible || prestamoId == null) return
    await cargarPdf(prestamoId)
  },
)

onBeforeUnmount(() => revocarUrl())

function revocarUrl() {
  if (pdfUrl.value) {
    URL.revokeObjectURL(pdfUrl.value)
    pdfUrl.value = null
  }
  pdfBlob = null
}

async function cargarPdf(prestamoId: number) {
  loading.value = true
  error.value = ''
  revocarUrl()
  try {
    pdfBlob = await fetchEstadoCuentaPdfBlob(prestamoId)
    pdfUrl.value = URL.createObjectURL(pdfBlob)
  } catch (e) {
    error.value = getApiErrorMessage(e, 'No se pudo cargar el PDF del estado de cuenta.')
  } finally {
    loading.value = false
  }
}

function cerrar() {
  emit('update:visible', false)
  revocarUrl()
}

async function compartir() {
  if (!pdfBlob) return
  const telefono = props.telefono?.trim()
  if (!telefono) {
    toast.add({
      severity: 'warn',
      summary: 'Compartir',
      detail: 'El cliente no tiene teléfono registrado.',
      life: 4000,
    })
    return
  }
  sharing.value = true
  try {
    const result = await compartirEstadoCuentaPdf({
      telefono,
      nombreCliente: props.nombreCliente || 'Cliente',
      numeroPrestamo: props.numeroPrestamo,
      pdfBlob,
    })
    if (result === 'failed') {
      toast.add({
        severity: 'warn',
        summary: 'Compartir',
        detail: 'No se pudo compartir. Verifique que el teléfono tenga formato válido (8 dígitos en Honduras).',
        life: 5000,
      })
    } else if (result === 'whatsapp') {
      toast.add({
        severity: 'info',
        summary: 'WhatsApp',
        detail: 'Se abrió WhatsApp y se descargó el PDF. Adjúntelo al chat con el cliente.',
        life: 6000,
      })
    }
  } finally {
    sharing.value = false
  }
}

function descargar() {
  if (!pdfBlob) return
  descargarEstadoCuentaPdf(pdfBlob, props.numeroPrestamo)
}
</script>

<template>
  <Dialog
    :visible="visible"
    header="Estado de cuenta (PDF)"
    modal
    :style="{ width: 'min(56rem, 98vw)' }"
    :content-style="{ padding: 0 }"
    @update:visible="(v: boolean) => (v ? emit('update:visible', true) : cerrar())"
  >
    <div class="pdf-dialog-body">
      <p v-if="error" class="pdf-dialog-error">{{ error }}</p>
      <p v-else-if="loading" class="pdf-dialog-loading">Cargando PDF…</p>
      <iframe
        v-else-if="pdfUrl"
        :src="pdfUrl"
        class="pdf-dialog-frame"
        title="Vista previa del estado de cuenta"
      />
    </div>
    <template #footer>
      <Button
        label="Compartir al cliente"
        icon="pi pi-share-alt"
        severity="success"
        :loading="sharing"
        :disabled="loading || !!error || !pdfBlob || !telefono?.trim()"
        @click="compartir"
      />
      <Button
        label="Descargar"
        icon="pi pi-download"
        severity="secondary"
        outlined
        :disabled="loading || !!error || !pdfBlob"
        @click="descargar"
      />
      <Button label="Cerrar" severity="secondary" text @click="cerrar" />
    </template>
  </Dialog>
</template>

<style scoped>
.pdf-dialog-body {
  min-height: min(70vh, 42rem);
  background: #f1f5f9;
}

.pdf-dialog-frame {
  display: block;
  width: 100%;
  min-height: min(70vh, 42rem);
  border: 0;
}

.pdf-dialog-loading,
.pdf-dialog-error {
  margin: 0;
  padding: 1.5rem;
}

.pdf-dialog-error {
  color: #b91c1c;
}
</style>
