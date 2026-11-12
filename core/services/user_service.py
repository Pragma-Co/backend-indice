from core.models import User


def list_active_users():
    return User.objects.filter(is_active=True).order_by("name", "id")
