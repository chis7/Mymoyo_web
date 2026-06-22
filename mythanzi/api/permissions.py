from rest_framework.permissions import BasePermission

from users.access import APPOINTMENT_ROLES, USER_ADMIN_ROLES, get_user_role


class IsActivePortalUser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        profile = getattr(user, 'profile', None)
        return bool(getattr(profile, 'is_active', user.is_active))


class CanManageUsers(IsActivePortalUser):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_superuser or get_user_role(request.user) in USER_ADMIN_ROLES


class CanUseAppointments(IsActivePortalUser):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.is_superuser or get_user_role(request.user) in APPOINTMENT_ROLES or request.method in {'GET', 'HEAD', 'OPTIONS'}

