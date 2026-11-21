"""Entrada de trabalho; os destinos continuam aplicando a autorização existente."""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.organizacao.autorizacao import exigir_operacao, setores_do_usuario


class LoginOperacional(LoginView):
    template_name = "planejamento/operacional/login.html"


class LogoutOperacional(LogoutView):
    next_page = "login_operacional"


def navegacao_operacional(usuario):
    setores = list(setores_do_usuario(usuario).order_by("nome"))

    def permite(permissao):
        try:
            exigir_operacao(usuario, permissao)
        except PermissionDenied:
            return False
        return True

    # Admin exige staff; uma permissão isolada não torna o destino acessível.
    apoio = usuario.is_staff and bool(setores)
    return {
        "setores_permitidos": setores,
        "pode_ver_semana": bool(setores) and permite("planejamento.view_alocacao"),
        "pode_planejar": apoio and permite("planejamento.add_alocacao"),
        "pode_ver_tarefas": apoio and permite("planejamento.view_tarefa"),
        "pode_ver_equipe": apoio and permite("organizacao.view_trabalhador"),
        "pode_cadastrar_trabalhador": apoio and permite("organizacao.add_trabalhador"),
    }


@login_required
@require_GET
def entrada(request):
    return render(request, "planejamento/operacional/inicio.html",
                  navegacao_operacional(request.user))
