"""URL configuration for config project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.auth_views import ThrottledTokenObtainPairView, ThrottledTokenRefreshView


def root_redirect(request):
    """Redirige a documentación en dev o health en producción."""
    if getattr(settings, 'OPENAPI_ENABLED', False):
        return redirect('/api/v1/docs/', permanent=False)
    return redirect('/api/v1/health/', permanent=False)


class OpenApiGuardMixin:
    """Oculta schema/Swagger cuando OPENAPI_ENABLED es False (producción)."""

    def dispatch(self, request, *args, **kwargs):
        if not getattr(settings, 'OPENAPI_ENABLED', False):
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class GuardedSpectacularAPIView(OpenApiGuardMixin, SpectacularAPIView):
    """Schema OpenAPI solo en entornos habilitados."""


class GuardedSpectacularSwaggerView(OpenApiGuardMixin, SpectacularSwaggerView):
    """UI Swagger solo en entornos habilitados."""


urlpatterns = [
    path('', root_redirect),
    path('api/v1/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/schema/', GuardedSpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', GuardedSpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/', include('api.urls')),
]

if getattr(settings, 'DJANGO_ENABLE_ADMIN', False):
    urlpatterns.insert(1, path(settings.DJANGO_ADMIN_URL, admin.site.urls))

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
