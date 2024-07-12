from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as django_logout
from django.http import JsonResponse
import boto3
import os
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime


from dotenv import load_dotenv
load_dotenv()

def login(request):
    return render(request,'login.html')

@login_required
def home(request):
    return render(request,'home.html')


def logout(request):
    django_logout(request)
    
    request.session.flush()
    return redirect('login')

def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        
        region_name=os.getenv('AWS_DEFAULT_REGION')
    )

def list_folders(request):
    s3_client=get_s3_client()
    
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Delimiter='/')
        
        
        folders = []
        files= []
        
        for common_prefix in response.get('CommonPrefixes', []):
            prefix = common_prefix['Prefix']
            subdirectory_info = {
                'folderName': prefix,
                'FileCount': 0,
                'FolderCount': 0,
                'LastModified': None
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
                    
            folders.append(subdirectory_info)


        for obj in response.get('Contents', []):
            file_info = {
                'fileName': obj['Key'],
                'LastModified': obj['LastModified']
            }
            files.append(file_info)

        folders_count=len(folders)
        files_count=len(files)

        return JsonResponse({'folders': folders,
                             'files': files,
                             'folder_count':folders_count,
                             'files_count':files_count
                             })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    



def list_files(request, folder_id):
    s3_client = get_s3_client()
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    try:
        folder_key = folder_id.rstrip('/') + '/'
        
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_key, Delimiter='/')
        
        files = []
        folders = []
        
        for obj in response.get('Contents', []):
            if obj['Key'] != folder_key:
                files.append({
                    'Key': obj['Key'],
                    'LastModified': obj['LastModified']
                })
        
        for common_prefix in response.get('CommonPrefixes', []):
            subfolder_key = common_prefix['Prefix']
            
            
            file_count = 0
            folder_count = 0
            last_modified = None
            
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket_name, Prefix=subfolder_key, Delimiter='/'):
                for obj in page.get('Contents', []):
                    if obj['Key'] != subfolder_key:  # this avoids folder to be counted as a file
                        file_count += 1
                        if last_modified is None or obj['LastModified'] > last_modified:
                            last_modified = obj['LastModified']
                
                for sub_prefix in page.get('CommonPrefixes', []):
                    folder_count += 1
            
            folders.append({
                'folderName': subfolder_key,
                'FileCount': file_count,
                'FolderCount': folder_count,
                'LastModified': last_modified
            })
        
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
        file_key = os.path.join(folder_id, file.name)
        try:
            bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
            s3_client = get_s3_client()
            s3_client.upload_fileobj(file, bucket_name, file_key)
            return JsonResponse({'message': 'File uploaded successfully'}, status=200)
        except (NoCredentialsError, PartialCredentialsError) as e:
            return JsonResponse({'error': str(e)}, status=403)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def delete_file(request, folder_id, file_name):
    file_key = os.path.join(folder_id, file_name)
    try:
        bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
        s3_client = get_s3_client()
        s3_client.delete_object(Bucket=bucket_name, Key=file_key)
        return JsonResponse({'message': 'File deleted successfully'}, status=200)
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
            s3_client.put_object(Bucket=os.getenv('AWS_STORAGE_BUCKET_NAME'), Key=folder_key)
            return JsonResponse({'message': 'Folder created successfully'}, status=200)
        except (NoCredentialsError, PartialCredentialsError) as e:
            return JsonResponse({'error': str(e)}, status=403)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)
       
