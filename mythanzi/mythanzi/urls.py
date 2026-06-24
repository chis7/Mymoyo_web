"""
URL configuration for mythanzi project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.http import FileResponse
from django.shortcuts import render
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from users import views as user_views


def vue_frontend(request, path=''):
    index_path = settings.FRONTEND_DIST_DIR / 'index.html'
    if index_path.exists():
        return FileResponse(index_path.open('rb'), content_type='text/html')
    return render(request, 'frontend/unbuilt.html')


urlpatterns = [
    path('', RedirectView.as_view(url='/users/dashboard/', permanent=False)),
    path('api/', include('api.urls')),
    path('api-auth/', include('rest_framework.urls')),
    path('app/', vue_frontend, name='vue_frontend'),
    re_path(r'^app/(?P<path>.*)$', vue_frontend, name='vue_frontend_fallback'),
    path('admin/', admin.site.urls),
    path('feedback/', user_views.clinic_feedback, name='clinic_feedback'),
    path('reminders/', user_views.medication_reminders, name='medication_reminders'),
    path('hivst/self-report/', user_views.self_test_report, name='self_test_report'),
    path('pv/client-report/', user_views.side_effect_report, name='side_effect_report'),
    path('self-screening/', user_views.self_risk_assessment, name='self_risk_assessment'),
    path('chatbot/', include('chatbot.urls')),
    path('facilities/', include('locations.urls')),
    path('users/', include('users.urls')),
]
