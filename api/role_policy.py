"""
Matriz de roles con permiso de escritura por recurso.

Mantener alineado con `front/src/composables/usePermissions.ts`.
"""

# Catálogos, clientes, préstamos, cuotas, servicios, usuarios, zonas, carteras
WRITE_ADMIN = ('administrador', 'supervisor')

# Cobros y pagos
WRITE_COBROS = ('administrador', 'supervisor', 'asesor', 'cobrador', 'cobranza_adm_jud')

# Anulación de cobros / facturas
WRITE_ANULAR_PAGOS = WRITE_ADMIN

# Documentos de cliente (expediente)
WRITE_DOCUMENTOS = WRITE_COBROS

# Contratos de préstamo
WRITE_CONTRATOS = ('administrador', 'supervisor', 'asesor')

# Configuración del sistema (facturación SAR, etc.)
WRITE_CONFIGURACION = WRITE_ADMIN
