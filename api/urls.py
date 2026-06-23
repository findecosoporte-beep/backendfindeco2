"""Rutas de la API de prestamos."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CarteraViewSet,
    ClienteViewSet,
    ClienteDocumentoViewSet,
    ContratoPrestamoViewSet,
    DashboardResumenView,
    HealthView,
    HistorialPrestamoViewSet,
    MeView,
    PagoViewSet,
    PrestamoViewSet,
    PrestamoCuotaViewSet,
    ServicioViewSet,
    SimulacionPrestamoView,
    UsuarioViewSet,
    ZonaViewSet,
)

router = DefaultRouter()
router.register(r'clientes', ClienteViewSet, basename='clientes')
router.register(r'cliente-documentos', ClienteDocumentoViewSet, basename='cliente-documentos')
router.register(r'contratos-prestamo', ContratoPrestamoViewSet, basename='contratos-prestamo')
router.register(r'usuarios', UsuarioViewSet, basename='usuarios')
router.register(r'prestamos', PrestamoViewSet, basename='prestamos')
router.register(r'prestamo-cuotas', PrestamoCuotaViewSet, basename='prestamo-cuotas')
router.register(r'pagos', PagoViewSet, basename='pagos')
router.register(r'servicios', ServicioViewSet, basename='servicios')
router.register(r'historial-prestamos', HistorialPrestamoViewSet, basename='historial-prestamos')
router.register(r'zonas', ZonaViewSet, basename='zonas')
router.register(r'carteras', CarteraViewSet, basename='carteras')

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('me/', MeView.as_view(), name='me'),
    path('dashboard/', DashboardResumenView.as_view(), name='dashboard'),
    path('prestamos/simular/', SimulacionPrestamoView.as_view(), name='prestamos-simular'),
    path('', include(router.urls)),
]
