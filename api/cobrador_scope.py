"""Alcance de datos para cobradores asignados por cartera."""

from django.db.models import QuerySet

from .models import Usuario, UsuarioCartera


def usuario_operativo_desde_request(request) -> Usuario | None:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return None
    email = (request.user.email or '').strip()
    if not email:
        return None
    return Usuario.objects.filter(correo__iexact=email).only('id_usuario', 'rol', 'correo').first()


def carteras_ids_para_usuario(usuario: Usuario | None) -> list[int]:
    if usuario is None or usuario.rol != 'cobrador':
        return []
    return list(
        UsuarioCartera.objects.filter(id_usuario=usuario).values_list('id_cartera_id', flat=True)
    )


def filtrar_prestamos_por_cobrador(qs: QuerySet, request) -> QuerySet:
    actor = usuario_operativo_desde_request(request)
    if actor is None or actor.rol != 'cobrador':
        return qs
    cartera_ids = carteras_ids_para_usuario(actor)
    if not cartera_ids:
        return qs.none()
    return qs.filter(id_cartera_id__in=cartera_ids)


def filtrar_pagos_por_cobrador(qs: QuerySet, request) -> QuerySet:
    """Pagos visibles para cobrador: solo préstamos de sus carteras."""
    actor = usuario_operativo_desde_request(request)
    if actor is None or actor.rol != 'cobrador':
        return qs
    cartera_ids = carteras_ids_para_usuario(actor)
    if not cartera_ids:
        return qs.none()
    return qs.filter(id_prestamo__id_cartera_id__in=cartera_ids)


def validar_cobro_por_cartera(request, prestamo) -> None:
    """Impide que un cobrador registre pagos fuera de sus carteras asignadas."""
    from rest_framework import serializers

    actor = usuario_operativo_desde_request(request)
    if actor is None or actor.rol != 'cobrador':
        return

    cartera_id = getattr(prestamo, 'id_cartera_id', None)
    if not cartera_id:
        raise serializers.ValidationError(
            {'id_prestamo': 'El préstamo no tiene cartera asignada; no se puede cobrar.'}
        )

    cartera_ids = carteras_ids_para_usuario(actor)
    if cartera_id not in cartera_ids:
        cartera = getattr(prestamo, 'id_cartera', None)
        nombre = (getattr(cartera, 'nombre', None) or '').strip() or f'#{cartera_id}'
        raise serializers.ValidationError(
            {
                'id_prestamo': (
                    f'No puede cobrar en la cartera «{nombre}»; no está asignada a su usuario.'
                )
            }
        )
