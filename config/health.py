from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health(request):
    """Sonda de processo sem dados internos, segredos ou consultas ao banco."""
    return JsonResponse({"status": "ok"})
