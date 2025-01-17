from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as django_logout
from django.http import JsonResponse
from datetime import datetime, timezone, timedelta
import boto3
import os
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime
import pytz
import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import requests
from django.conf import settings
import time
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import NoCredentialsError, PartialCredentialsError


from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    token = request.data.get('token')
    
    if not token:
        logger.error('No token provided')
        return Response({'success': False, 'error': 'No token provided'}, status=400)

    try:
        response = requests.get(f'https://www.googleapis.com/oauth2/v3/tokeninfo?access_token={token}')
        
        if response.status_code != 200:
            logger.error(f'Invalid token: {response.json()}')
            return Response({'success': False, 'error': f'Invalid token: {response.json()}'}, status=400)
        
        idinfo = response.json()
        
        if idinfo['aud'] != settings.GOOGLE_OAUTH2_CLIENT_ID:
            logger.error(f'Unauthorized: {idinfo["aud"]}')
            return Response({'success': False, 'error': 'Unauthorized'}, status=400)
        email = idinfo['email']
        name = idinfo.get('name', '')
        return Response({
            'success': True,
            'token': token,
            'user': {
                'email': email,
                'name': name
            }
        })
    except ValueError as e:
        logger.error(f'Invalid token: {str(e)}')
        return Response({'success': False, 'error': f'Invalid token: {str(e)}'}, status=400)
    except Exception as e:
        logger.error(f'Unexpected error: {str(e)}')
        return Response({'success': False, 'error': f'Unexpected error: {str(e)}'}, status=400)
    
    
    
    

@api_view(['GET'])
def protected_view(request):
    user_info = request.user_info
    return Response({'success': True, 'user': user_info})

def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        
        region_name=os.getenv('AWS_DEFAULT_REGION')
    )

def parse_date(date_str):
    for fmt in ('%Y-%m-%d %H:%M:%S%z', '%Y-%m-%dT%H:%M:%S.%fZ'):
        try:
            date = datetime.strptime(date_str, fmt)
            if date.tzinfo is None:
                date = date.replace(tzinfo=pytz.UTC)
            return date
        except ValueError:
            continue
    return None



def process_folder(s3_client, bucket_name, prefix):
    subdirectory_info = {
        'folderName': prefix,
        'FileCount': 0,
        'FolderCount': 0,
        'LastModified': None,
        'CreatedAt': None 
    }

    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix, Delimiter='/'):
        for obj in page.get('Contents', []):
            if not obj['Key'].endswith('/'):
                subdirectory_info['FileCount'] += 1
                if (subdirectory_info['LastModified'] is None or
                        obj['LastModified'] > subdirectory_info['LastModified']):
                    subdirectory_info['LastModified'] = obj['LastModified']

        for sub_prefix in page.get('CommonPrefixes', []):
            subdirectory_info['FolderCount'] += 1

    try:
        head_response = s3_client.head_object(Bucket=bucket_name, Key=prefix)
        created_at = head_response.get('Metadata', {}).get('createdat')
        if created_at:
            subdirectory_info['CreatedAt'] = parse_date(created_at)
    except s3_client.exceptions.ClientError as e:
        logger.error(f"Error fetching metadata for {prefix}: {e}")

    if subdirectory_info['FileCount'] == 0 and subdirectory_info['FolderCount'] == 0:
        subdirectory_info['LastModified'] = subdirectory_info['CreatedAt']

    return subdirectory_info


@csrf_exempt
def search(request):
    if request.method == 'GET':
        query = request.GET.get('q', '')
        file_type = request.GET.get('type', None) 

        if not query:
            return JsonResponse({'error': 'Query parameter is required'}, status=400)

        s3_client = get_s3_client()
        bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')

        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            result = {
                'files': [],
                'folders': []
            }

            folders_set = set()

            for page in paginator.paginate(Bucket=bucket_name, Prefix=''):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    
                    if query.lower() in key.lower():
                        
                        if key.endswith('/'):
                            
                            folder_parts = key.strip('/').split('/')
                            if query.lower() in folder_parts[-1].lower():
                                result['folders'].append(key)
                                folders_set.add(key)
                        else:
                            if file_type:
                                if key.lower().endswith(file_type.lower()):
                                    result['files'].append(key)
                            else:
                                result['files'].append(key)

            
            result['files'] = [file for file in result['files'] if not any(file.startswith(folder) for folder in folders_set)]

            return JsonResponse(result, status=200)
        except (NoCredentialsError, PartialCredentialsError) as e:
            return JsonResponse({'error': str(e)}, status=403)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)
def list_folders(request):
    start = time.time()

    s3_client = get_s3_client()
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')

    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Delimiter='/')

        folders = []
        files = []

        common_prefixes = response.get('CommonPrefixes', [])
        with ThreadPoolExecutor() as executor:
            folder_futures = [executor.submit(process_folder, s3_client, bucket_name, cp['Prefix']) for cp in common_prefixes]
            for future in folder_futures:
                folders.append(future.result())

        for obj in response.get('Contents', []):
            file_info = {
                'fileName': obj['Key'],
                'LastModified': obj['LastModified']
            }
            files.append(file_info)

        folders = sorted(folders, key=lambda x: (x['LastModified'] if x['LastModified'] is not None else datetime.min.replace(tzinfo=pytz.UTC)), reverse=True)
        files = sorted(files, key=lambda x: (x['LastModified'] if x['LastModified'] is not None else datetime.min.replace(tzinfo=pytz.UTC)), reverse=True)

        folders_count = len(folders)
        files_count = len(files)

        return JsonResponse({
            'folders': folders,
            'files': files,
            'folder_count': folders_count,
            'files_count': files_count
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def process_subfolder_page(page):
    file_count = 0
    folder_count = 0
    last_modified = None

    for obj in page.get('Contents', []):
        if not obj['Key'].endswith('/'):
            file_count += 1
            if last_modified is None or obj['LastModified'] > last_modified:
                last_modified = obj['LastModified']

    for sub_prefix in page.get('CommonPrefixes', []):
        folder_count += 1

    return file_count, folder_count, last_modified

def list_files(request, folder_id):
    s3_client = get_s3_client()
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
    bucket_region = os.getenv('AWS_DEFAULT_REGION')

    try:
        folder_key = folder_id.rstrip('/') + '/'
        
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_key, Delimiter='/')
        
        files = []
        folders = []

        for obj in response.get('Contents', []):
            if obj['Key'] != folder_key:
                file_info = {
                    'Key': obj['Key'],
                    'LastModified': obj['LastModified'],
                    'URL': f'https://{bucket_name}.s3.{bucket_region}.amazonaws.com/{obj["Key"]}'
                }
                files.append(file_info)

        def process_common_prefix(common_prefix):
            subfolder_key = common_prefix['Prefix']
            paginator = s3_client.get_paginator('list_objects_v2')
            subfolder_pages = paginator.paginate(Bucket=bucket_name, Prefix=subfolder_key, Delimiter='/')
            file_count = 0
            folder_count = 0
            last_modified = None
            created_at = None  
            for page in subfolder_pages:
                page_file_count, page_folder_count, page_last_modified = process_subfolder_page(page)
                file_count += page_file_count
                folder_count += page_folder_count
                if last_modified is None or (page_last_modified is not None and page_last_modified > last_modified):
                    last_modified = page_last_modified
            
            try:
                head_response = s3_client.head_object(Bucket=bucket_name, Key=subfolder_key)
                created_at = head_response.get('Metadata', {}).get('createdat')
                if created_at:
                    created_at = parse_date(created_at)
            except s3_client.exceptions.ClientError as e:
                logger.error(f"Error fetching metadata for {subfolder_key}: {e}")

            if file_count == 0 and folder_count == 0:
                last_modified = created_at

            return {
                'folderName': subfolder_key,
                'FileCount': file_count,
                'FolderCount': folder_count,
                'LastModified': last_modified
            }

        with ThreadPoolExecutor() as executor:
            subfolder_results = list(executor.map(process_common_prefix, response.get('CommonPrefixes', [])))

        folders.extend(subfolder_results)
        
        files = sorted(files, key=lambda x: (x['LastModified'] if x['LastModified'] is not None else datetime.min.replace(tzinfo=pytz.UTC)), reverse=True)
        folders = sorted(folders, key=lambda x: (x['LastModified'] if x['LastModified'] is not None else datetime.min.replace(tzinfo=pytz.UTC)), reverse=True)

        file_count = len(files)
        folder_count = len(folders)

        return JsonResponse({
            'folder_id': folder_id,
            'files': files,
            'folders': folders,
            'file_count': file_count,
            'folder_count': folder_count
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)




@csrf_exempt
def upload_file(request):
    if request.method == 'POST' and request.FILES['file']:
        folder_id = request.POST.get('folder_id')
        file = request.FILES['file']
        file_name=request.POST.get('file_name',file.name)
        file_key = os.path.join(folder_id, file_name)
        try:
            bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
            s3_client = get_s3_client()

            existing_files=s3_client.list_objects_v2(Bucket=bucket_name,Prefix=file_key)
            if 'Contents' in existing_files:
                return JsonResponse({'error': 'A file with the same name already exists'}, status=400)


            s3_client.upload_fileobj(file, bucket_name, file_key)
            return JsonResponse({'message': 'File uploaded successfully'}, status=200)
        except (NoCredentialsError, PartialCredentialsError) as e:
            return JsonResponse({'error': str(e)}, status=403)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def delete_file(request, folder_id, file_name=None):
    s3_client = get_s3_client()
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    try:
        if file_name:
            file_key = os.path.join(folder_id, file_name)
            s3_client.delete_object(Bucket=bucket_name, Key=file_key)
            return JsonResponse({'message': 'File deleted successfully'}, status=200)
        else:
            folder_key = folder_id.rstrip('/') + '/'
            objects_to_delete = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_key)
            
            if 'Contents' in objects_to_delete:
                delete_keys = [{'Key': obj['Key']} for obj in objects_to_delete['Contents']]
                s3_client.delete_objects(Bucket=bucket_name, Delete={'Objects': delete_keys})
                return JsonResponse({'message': 'Folder and all its contents deleted successfully'}, status=200)
            else:
                return JsonResponse({'error': 'Folder not found or empty'}, status=404)
    except (NoCredentialsError, PartialCredentialsError) as e:
        return JsonResponse({'error': str(e)}, status=403)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def create_folder(request):
    if request.method == 'POST':
        parent_folder = request.POST.get('parent_folder', '')
        folder_name = request.POST.get('folder_name')
        if not folder_name:
            return JsonResponse({'error': 'Folder name is required'}, status=400)

        
        folder_key = os.path.join(parent_folder, folder_name).rstrip('/') + '/'

        try:
            s3_client = get_s3_client()
            bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
            response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_key, Delimiter='/')
            if 'CommonPrefixes' in response or 'Contents' in response:
                return JsonResponse({'error': 'Folder with the same name already exists'}, status=400)
            created_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S%z')
            created_at = created_at[:-2] + ':' + created_at[-2:]
            s3_client.put_object(Bucket=os.getenv('AWS_STORAGE_BUCKET_NAME'), Key=folder_key, Metadata={'createdAt': created_at})
            return JsonResponse({'message': 'Folder created successfully'}, status=200)
        except (NoCredentialsError, PartialCredentialsError) as e:
            return JsonResponse({'error': str(e)}, status=403)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)
       
