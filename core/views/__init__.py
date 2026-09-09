"""HTTP endpoints of the core app, one module per resource."""

from core.views.health_view import api_root, health_check

__all__ = ["api_root", "health_check"]
