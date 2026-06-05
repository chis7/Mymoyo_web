"""
URL configuration for mymoyo project.

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
from django.urls import path, include
from django.views.generic import RedirectView
from users import views as user_views

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='portal_home', permanent=False)),
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
