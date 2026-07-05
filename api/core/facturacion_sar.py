"""Numeracion y validacion de facturas segun formato SAR (Honduras)."""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from api.models import ConfiguracionFacturacion, Pago


class ErrorFacturacionSAR(Exception):
    """Error de configuracion o rango de facturacion SAR."""


def formatear_numero_factura_sar(
    establecimiento: str,
    punto_emision: str,
    tipo_documento: str,
    correlativo: int,
) -> str:
    """Formato oficial: XXX-XXX-XX-XXXXXXXX."""
    est = str(establecimiento or '001').zfill(3)[-3:]
    punto = str(punto_emision or '001').zfill(3)[-3:]
    tipo = str(tipo_documento or '01').zfill(2)[-2:]
    return f'{est}-{punto}-{tipo}-{int(correlativo):08d}'


def formatear_correlativo_rango(correlativo: int) -> str:
    """Correlativo de 8 digitos para rango autorizado en factura impresa."""
    return f'{int(correlativo):08d}'


def obtener_configuracion_facturacion() -> ConfiguracionFacturacion:
    """Singleton de configuracion fiscal (pk=1)."""
    config, _ = ConfiguracionFacturacion.objects.get_or_create(pk=1)
    return config


def _validar_configuracion_activa(config: ConfiguracionFacturacion, fecha_ref: date | None = None) -> None:
    if not config.usar_numeracion_sar:
        return
    if not config.razon_social.strip():
        raise ErrorFacturacionSAR('Configure la razon social del emisor antes de facturar.')
    if not config.rtn.strip():
        raise ErrorFacturacionSAR('Configure el RTN del emisor antes de facturar.')
    if not config.cai.strip():
        raise ErrorFacturacionSAR('Configure el CAI autorizado por SAR antes de facturar.')
    if config.fecha_limite_emision is None:
        raise ErrorFacturacionSAR('Configure la fecha limite de emision del CAI.')
    hoy = fecha_ref or timezone.localdate()
    if hoy > config.fecha_limite_emision:
        raise ErrorFacturacionSAR('La fecha limite de emision del CAI ha vencido.')
    if config.correlativo_actual > config.correlativo_hasta:
        raise ErrorFacturacionSAR('Se agoto el rango autorizado de facturacion SAR.')
    if config.correlativo_actual < config.correlativo_desde:
        raise ErrorFacturacionSAR(
            'El correlativo actual esta por debajo del rango autorizado. Ajuste la configuracion.',
        )


def asignar_numero_factura_sar(pago: Pago) -> str | None:
    """
    Reserva el siguiente numero SAR para un cobro con factura propia.

    Solo aplica al pago maestro (no lineas hijas vinculadas a otra factura).
    Debe invocarse dentro de una transaccion con bloqueo de fila en configuracion.
    """
    if pago.numero_factura:
        return pago.numero_factura
    if getattr(pago, 'id_pago_factura_id', None):
        return None

    config, _ = ConfiguracionFacturacion.objects.select_for_update().get_or_create(pk=1)
    if not config.usar_numeracion_sar:
        return None

    _validar_configuracion_activa(config, pago.fecha_pago)

    correlativo = int(config.correlativo_actual)
    numero = formatear_numero_factura_sar(
        config.establecimiento,
        config.punto_emision,
        config.tipo_documento,
        correlativo,
    )
    pago.numero_factura = numero
    pago.save(update_fields=['numero_factura'])

    config.correlativo_actual = correlativo + 1
    config.save(update_fields=['correlativo_actual', 'actualizado_en'])
    return numero


def texto_rango_autorizado(config: ConfiguracionFacturacion) -> str:
    """Leyenda de rango autorizado para pie de factura."""
    desde = formatear_numero_factura_sar(
        config.establecimiento,
        config.punto_emision,
        config.tipo_documento,
        config.correlativo_desde,
    )
    hasta = formatear_numero_factura_sar(
        config.establecimiento,
        config.punto_emision,
        config.tipo_documento,
        config.correlativo_hasta,
    )
    return f'Del {desde} al {hasta}'
