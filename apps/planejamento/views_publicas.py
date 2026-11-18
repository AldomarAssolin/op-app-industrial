from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_safe


def _pagina(request, template):
    if not settings.OP_APP_PUBLIC_PAGES_ENABLED:
        raise Http404
    contato = settings.OP_APP_SUPPORT_EMAIL
    try:
        validate_email(contato)
    except ValidationError as erro:
        # Não publicar um aviso de privacidade sem contato público válido.
        raise Http404 from erro
    return render(request, template, {"support_email": contato})


@require_safe
def inicio(request):
    return _pagina(request, "planejamento/publico/inicio.html")


@require_safe
def privacidade(request):
    return _pagina(request, "planejamento/publico/privacidade.html")
