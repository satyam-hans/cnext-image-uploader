from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LogoutView  
from mainApp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('social-auth/', include('social_django.urls', namespace='social')),
    path("", views.home, name='home'),


    path('list-folders/', views.list_folders, name='list-folders'),
    path('list-files/<str:folder_id>/', views.list_files, name='list-files'),
    path('upload-file/', views.upload_file, name='upload-file'),
    path('delete-file/<str:folder_id>/<str:file_name>/', views.delete_file, name='delete-file'),
    path('create-folder/', views.create_folder, name='create-folder'),
]
