"""Vistas JWT con rate limiting."""

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from api.throttling import LoginRateThrottle, LoginUserRateThrottle


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Login: throttle por IP para mitigar fuerza bruta."""

    throttle_classes = (LoginRateThrottle,)


class ThrottledTokenRefreshView(TokenRefreshView):
    """Refresh: throttle por IP y por usuario."""

    throttle_classes = (LoginRateThrottle, LoginUserRateThrottle)
