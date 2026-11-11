"""Señales que invalidan caches derivados de préstamos y pagos."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Pago, Prestamo, PrestamoCuota
from .resumen_cache import invalidar_resumen_carteras


@receiver([post_save, post_delete], sender=Pago)
@receiver([post_save, post_delete], sender=Prestamo)
@receiver([post_save, post_delete], sender=PrestamoCuota)
def _invalidar_resumen_carteras(sender, **kwargs):
    invalidar_resumen_carteras()
