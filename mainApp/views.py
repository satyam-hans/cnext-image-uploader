from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as django_logout

# Create your views here.

def login(request):
    return render(request,'login.html')

@login_required
def home(request):
    return render(request,'home.html')

#logout
def logout(request):
    django_logout(request)
    # Clear all session data
    request.session.flush()
    return redirect('login')