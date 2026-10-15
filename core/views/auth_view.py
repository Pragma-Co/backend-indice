from django.contrib.auth import logout
from django.http import HttpResponse
from django.views.decorators.http import require_POST


@require_POST
def logout_view(request):
    logout(request)
    return HttpResponse(status=204)
