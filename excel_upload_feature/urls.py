from django.urls import path
from .view import ExcelUploadView

urlpatterns = [
    path('upload/', ExcelUploadView.as_view(), name='excel_upload'),
]