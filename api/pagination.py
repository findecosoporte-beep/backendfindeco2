"""Paginadores DRF compatibles con clientes SPA (sin 404 típico de página inválida)."""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StablePageNumberPagination(PageNumberPagination):
    """
    Django REST Framework, con ``PageNumberPagination``, responde 404 si ``?page=``
    apunta más allá del último lote («Invalid page»).

    Esta clase usa ``Paginator.get_page()`` para obtener siempre una página válida
    y añade el campo ``page`` con el número efectivo, de modo que el front puede
    alinear estado y paginador.
    """

    def paginate_queryset(self, queryset, request, view=None):
        self.request = request
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        paginator = self.django_paginator_class(queryset, page_size)
        page_number = self.get_page_number(request, paginator)
        self.page = paginator.get_page(page_number)

        if paginator.num_pages > 1 and self.template is not None:
            self.display_page_controls = True

        return list(self.page)

    def get_paginated_response(self, data):
        return Response(
            {
                'count': self.page.paginator.count,
                'page': self.page.number,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'results': data,
            }
        )
