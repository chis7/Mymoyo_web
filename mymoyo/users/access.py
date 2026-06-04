from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import UserProfile


USER_ADMIN_ROLES = {'admin'}
DASHBOARD_ROLES = {'admin', 'supervisor'}
APPOINTMENT_ROLES = {'admin', 'supervisor', 'provider', 'chw', 'mobiliser'}


def get_user_role(user):
    if user.is_superuser:
        return 'admin'

    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile.role


def active_login_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_superuser:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if not profile.is_active:
                raise PermissionDenied
            allowed_names = {'password_change_required', 'logout'}
            if profile.must_change_password and request.resolver_match.url_name not in allowed_names:
                return redirect('password_change_required')

        return view_func(request, *args, **kwargs)

    return wrapped_view


def role_required(*allowed_roles):
    def decorator(view_func):
        @active_login_required
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser or get_user_role(request.user) in allowed_roles:
                return view_func(request, *args, **kwargs)

            raise PermissionDenied

        return wrapped_view

    return decorator
