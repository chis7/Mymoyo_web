from django.contrib.auth.backends import ModelBackend
from django.utils import timezone


class TemporaryPasswordBackend(ModelBackend):
    """Reject authentication when an admin-generated temporary password has expired."""

    def user_can_authenticate(self, user):
        can_authenticate = super().user_can_authenticate(user)
        if not can_authenticate:
            return False

        profile = getattr(user, 'profile', None)
        expires_at = getattr(profile, 'temporary_password_expires_at', None)
        return not (expires_at and expires_at <= timezone.now())
