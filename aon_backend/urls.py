from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/user/',include('users.urls')),
    path('api/content/',include('content.urls')),
    path('api/assessment/',include('assessment.urls')),
    path('api/session/',include('session.urls')),
    path('api/candidate/',include('candidate.urls')),
    path('api/dashboard/',include('dashboard.urls')),
]
