# excel_upload_features/view.py

from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework import status
import os
import uuid
import zipfile
import shutil  

from .process_excel import run_preprocessing_pipeline


class ExcelUploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request, format=None):
        zip_file = request.FILES.get('file')

        if not zip_file or not zip_file.name.endswith('.zip'):
            return Response(
                {'error': 'Please upload a .zip file containing Excel files.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 1: Save uploaded zip file temporarily
        upload_dir = 'uploaded_zips'
        os.makedirs(upload_dir, exist_ok=True)

        zip_path = os.path.join(upload_dir, 'demo_upload.zip')

        # Overwrite the file if it already exists
        with open(zip_path, 'wb+') as f:
            for chunk in zip_file.chunks():
                f.write(chunk)

        # Step 2: Extract zip contents
        extracted_dir = os.path.join(upload_dir, 'demo_unzipped')
        if os.path.exists(extracted_dir):
            shutil.rmtree(extracted_dir)
        os.makedirs(extracted_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_dir)

            # Step 3: Define fixed output Excel path
            os.makedirs("media", exist_ok=True)
            output_path = os.path.join("media", "demo_result.xlsx")

            # Step 4: Run preprocessing
            run_preprocessing_pipeline(
                excel_folder_path=extracted_dir,
                output_excel_path=output_path
            )

            return Response({
                'message': 'Folder processed successfully.',
                'download_url': f'/media/demo_result.xlsx'
            })

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
