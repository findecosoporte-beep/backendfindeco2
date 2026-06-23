"""Permisos de acceso por rol para los endpoints de la API.

La matriz de roles por recurso está en `api.role_policy` (alineada con el front).
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario
from .role_policy import WRITE_ADMIN


class RoleBasedAccessPermission(BasePermission):
    """Permite escritura solo a roles autorizados por vista."""

    message = 'No tienes permisos para ejecutar esta accion.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method in SAFE_METHODS:
            return True

        required_roles = getattr(view, 'required_write_roles', WRITE_ADMIN)
        actor = Usuario._default_manager.filter(correo=request.user.email).only('rol').first()
        if actor is None:
            self.message = 'El usuario autenticado no esta vinculado a un perfil operativo.'
            return False

        if actor.rol not in required_roles:
            self.message = f'Rol "{actor.rol}" no autorizado para escritura en este recurso.'
            return False

        return True
