from threading import local


_audit_context = local()


def get_current_audit_user():
    user = getattr(_audit_context, 'user', None)
    if user is not None and user.is_authenticated:
        return user
    return None


class AuditUserMiddleware:
    """Expose the current authenticated user to audit signal handlers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _audit_context.user = getattr(request, 'user', None)
        try:
            return self.get_response(request)
        finally:
            _audit_context.user = None
