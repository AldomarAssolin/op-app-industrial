"""Entrada de trabalho; os destinos continuam aplicando a autorização existente."""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.organizacao.autorizacao import setores_do_usuario, turnos_permitidos, pode_manter_equipe
from .orientacao import permite, proximo_passo


class LoginOperacional(LoginView):
    template_name = "planejamento/operacional/login.html"


class LogoutOperacional(LogoutView):
    next_page = "login_operacional"


def navegacao_operacional(usuario):
    setores = list(setores_do_usuario(usuario).order_by("nome"))

    # Admin exige staff; uma permissão isolada não torna o destino acessível.
    apoio = usuario.is_staff and bool(setores)
    return {
        "setores_permitidos": setores,
        "turnos_habilitados": settings.OP_APP_TURNOS_ENABLED,
        "setores_com_turnos": [{"setor": s, "turnos": sorted(turnos_permitidos(usuario, s.pk))} for s in setores] if settings.OP_APP_TURNOS_ENABLED else [],
        "pode_ver_semana": bool(setores) and permite(usuario, "planejamento.view_alocacao"),
        "pode_planejar": apoio and permite(usuario, "planejamento.add_alocacao"),
        "pode_ver_tarefas": apoio and permite(usuario, "planejamento.view_tarefa"),
        "pode_ver_equipe": apoio and permite(usuario, "organizacao.view_trabalhador"),
        "pode_cadastrar_trabalhador": apoio and permite(usuario, "organizacao.add_trabalhador") and (not settings.OP_APP_TURNOS_ENABLED or pode_manter_equipe(usuario)),
    }


@login_required
@require_GET
def entrada(request):
    return render(request, "planejamento/operacional/inicio.html",
                  {**navegacao_operacional(request.user), "orientacao": proximo_passo(request.user)})
