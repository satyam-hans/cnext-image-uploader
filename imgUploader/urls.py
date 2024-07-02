from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LogoutView  # Import LogoutView
from mainApp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('social-auth/', include('social_django.urls', namespace='social')),
    path("", views.home, name='home'),
]
