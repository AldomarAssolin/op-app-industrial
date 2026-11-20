from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_safe


def _contato_integracao():
    if not settings.OP_APP_PUBLIC_PAGES_ENABLED:
        return None
    contato = settings.OP_APP_SUPPORT_EMAIL
    try:
        validate_email(contato)
    except ValidationError:
        # Não publicar um aviso de privacidade sem contato público válido.
        return None
    return contato


def _pagina_integracao(request, template):
    contato = _contato_integracao()
    if contato is None:
        raise Http404
    return render(request, template, {"support_email": contato, "integration_enabled": True})


@require_safe
def inicio(request):
    if not settings.OP_APP_PRODUCT_HOME_ENABLED:
        # Compatibilidade durante a atualização do endereço no Google Branding.
        return _pagina_integracao(request, "planejamento/publico/backup.html")
    contato = _contato_integracao()
    return render(request, "planejamento/publico/inicio.html", {
        "support_email": contato,
        "integration_enabled": contato is not None,
        "product_home": True,
    })


@require_safe
def backup(request):
    return _pagina_integracao(request, "planejamento/publico/backup.html")


@require_safe
def privacidade(request):
    return _pagina_integracao(request, "planejamento/publico/privacidade.html")
