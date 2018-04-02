from django.shortcuts import render
from rest_framework import viewsets


class ExtendableModelMixin(object):
    def extend_response_data(self, data):
        raise NotImplementedError()

    def list(self, request, *args, **kwargs):
        """
        Returns list of pinned posts.
        ---
        """
        response = super().list(self, request, *args, **kwargs)
        self.extend_response_data(response.data.get('results'))

        return response

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(self, request, *args, **kwargs)

        self.extend_response_data([response.data])

        return response
