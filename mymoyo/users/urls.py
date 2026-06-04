from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.portal_home, name='portal_home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('change-password/', views.password_change_required, name='password_change_required'),
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='users/password_reset_form.html',
            email_template_name='users/password_reset_email.html',
            subject_template_name='users/password_reset_subject.txt',
            success_url='/users/password-reset/done/',
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(template_name='users/password_reset_done.html'),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='users/password_reset_confirm.html',
            success_url='/users/reset/done/',
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(template_name='users/password_reset_complete.html'),
        name='password_reset_complete',
    ),
    path('logout/', views.logout_view, name='logout'),
    path('auto-logout/', views.auto_logout_view, name='auto_logout'),
    path('session/status/', views.session_status, name='session_status'),
    path('theme/', views.update_theme, name='update_theme'),
    path('dashboard/', views.user_dashboard, name='user_dashboard'),
    path('manage/', views.user_list, name='user_list'),
    path('manage/stats/', views.user_management_stats, name='user_management_stats'),
    path('manage/rows/', views.user_management_rows, name='user_management_rows'),
    path('history/<str:app_label>/<str:model_name>/<str:object_pk>/events/', views.object_history_events, name='object_history_events'),
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('create/', views.user_create, name='user_create'),
    path('<int:pk>/', views.user_detail, name='user_detail'),
    path('<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('<int:pk>/reset-password/', views.user_reset_password, name='user_reset_password'),
    path('<int:pk>/delete/', views.user_delete, name='user_delete'),
]
