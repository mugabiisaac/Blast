from datetime import datetime

from django.template import loader
from rest_framework.compat import template_render
from rest_framework.pagination import PageNumberPagination, _positive_int, BasePagination
from rest_framework.request import Request
from rest_framework.response import Response
from collections import OrderedDict


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 250


class DateTimePaginator(BasePagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

    page_parameter = 'date'

    template = 'rest_framework/pagination/numbers.html'

    def get_page_size(self, request):
        if self.page_size_query_param:
            try:
                value = int(request.query_params.get(self.page_size_query_param, self.max_page_size))
                value = min(value, self.max_page_size)
                return value
            except (KeyError, ValueError):
                pass

        return self.page_size

    def get_page_parameter(self, request: Request):
        return request.query_params.get(self.page_parameter, datetime.now())

    def paginate_queryset(self, queryset, request, view=None):  # pragma: no cover
        page_size = self.get_page_size(request)
        date = self.get_page_parameter(request)

        qs = queryset.filter(created_at__lt=date)

        return qs[:page_size]

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('results', data)
        ]))

    def to_html(self):
        template = loader.get_template(self.template)
        context = {}
        return template_render(template, context)

    def get_results(self, data):
        return data['results']
