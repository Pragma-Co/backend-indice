import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from core.serializers.access_group_serializer import serialize_group, serialize_member
from core.services.access_group_service import list_active_groups
from core.services.access_group_management_service import (
    GroupManagementError,
    add_member,
    create_group,
    get_group,
    groups_for_manager,
    remove_member,
)
from core.services.revision_review_service import is_revision_reviewer


@require_http_methods(["GET"])
def access_group_options_view(request):
    if not (request.user.is_authenticated and request.user.is_active):
        return JsonResponse({"error": "AuthenticationRequired"}, status=401)
    return JsonResponse(
        [
            {
                "id": group.pk,
                "name": group.name,
                "scope": group.scope,
                "area": group.area.acronym if group.area else None,
                "secrecy_level": group.secrecy_level_id,
            }
            for group in list_active_groups()
        ],
        safe=False,
    )


def _manager_error(request):
    if not (request.user.is_authenticated and request.user.is_active):
        return JsonResponse({"error": "AuthenticationRequired"}, status=401)
    if not is_revision_reviewer(request.user) or not request.user.area.active:
        return JsonResponse({"error": "PermissionDenied"}, status=403)
    return None


def _error_response(error):
    if error.errors is not None:
        return JsonResponse({"errors": error.errors}, status=error.status)
    return JsonResponse({"error": error.code}, status=error.status)


def _payload(request):
    try:
        return json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GroupManagementError("InvalidJSON") from None


@require_http_methods(["GET", "POST"])
def access_groups_view(request):
    error = _manager_error(request)
    if error:
        return error
    try:
        if request.method == "GET":
            groups = groups_for_manager(request.user)
            return JsonResponse({"results": [serialize_group(group) for group in groups]})
        group = create_group(request.user, _payload(request))
        return JsonResponse(serialize_group(group), status=201)
    except GroupManagementError as exc:
        return _error_response(exc)


@require_http_methods(["GET", "POST"])
def access_group_users_view(request, group_id):
    error = _manager_error(request)
    if error:
        return error
    try:
        if request.method == "GET":
            group = get_group(request.user, group_id)
            memberships = group.memberships.select_related("user").order_by("user__name", "user_id")
            return JsonResponse({"results": [serialize_member(member) for member in memberships]})
        member = add_member(request.user, group_id, _payload(request))
        return JsonResponse(serialize_member(member), status=201)
    except GroupManagementError as exc:
        return _error_response(exc)


@require_http_methods(["DELETE"])
def access_group_user_view(request, group_id, user_id):
    error = _manager_error(request)
    if error:
        return error
    try:
        remove_member(request.user, group_id, user_id)
    except GroupManagementError as exc:
        return _error_response(exc)
    return HttpResponse(status=204)
