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
    print("AWS_ACCESS_KEY_ID:", os.getenv('AWS_ACCESS_KEY_ID'))
    print("AWS_SECRET_ACCESS_KEY:", os.getenv('AWS_SECRET_ACCESS_KEY'))
    print("AWS_STORAGE_BUCKET_NAME:", os.getenv('AWS_STORAGE_BUCKET_NAME'))
    print("AWS_DEFAULT_REGION:", os.getenv('AWS_DEFAULT_REGION'))
    s3_client=get_s3_client()
    print(s3_client)
    
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    try:
        print("abs")
        response = s3_client.list_objects_v2(Bucket=bucket_name, Delimiter='/')
        print(response)
        folders = []
        for common_prefix in response.get('CommonPrefixes', []):
         folders.append(common_prefix['Prefix'])

        folders_count=len(folders)
        return JsonResponse({'folders': folders,
                             'folder_count':folders_count
                             })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    



def list_files(request, folder_id):
    s3_client = get_s3_client()
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    try:
        folder_key = folder_id + '/'
        
        
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_key)
        
        files = []
        for obj in response.get('Contents', []):
            if obj['Key'] != folder_key:
             files.append({
                'Key': obj['Key'],
                'LastModified': obj['LastModified']
            })
        
        
        file_count = len(files)
        
        return JsonResponse({
            'folder_id': folder_id,
            'files': files,
            'file_count': file_count
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
        folder_name = request.POST.get('folder_name')
        folder_key = folder_name.rstrip('/') + '/'
        
        try:
            s3_client = get_s3_client()
            s3_client.put_object(Bucket=os.getenv('AWS_STORAGE_BUCKET_NAME'), Key=folder_key)
            return JsonResponse({'message': 'Folder created successfully'}, status=200)
        except (NoCredentialsError, PartialCredentialsError) as e:
            return JsonResponse({'error': str(e)}, status=403)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)       
