"""Manejador centralizado de errores para respuestas API consistentes."""

from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Transforma errores DRF a un formato uniforme."""
    response = exception_handler(exc, context)
    if response is None:
        return response

    default_message = 'Error en la solicitud.'
    if isinstance(response.data, dict):
        if 'detail' in response.data:
            default_message = str(response.data['detail'])
    elif isinstance(response.data, list) and response.data:
        default_message = str(response.data[0])

    response.data = {
        'success': False,
        'error': {
            'code': f'http_{response.status_code}',
            'message': default_message,
            'details': response.data,
        },
    }
    return response
