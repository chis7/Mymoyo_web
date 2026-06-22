from django.urls import path

from . import views


urlpatterns = [
    path('message/', views.chat_message, name='chatbot_message'),
]

