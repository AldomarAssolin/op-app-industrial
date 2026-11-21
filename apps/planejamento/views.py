from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .views_operacionais import navegacao_operacional
from .orientacao import proximo_passo
from .models import Alocacao
from apps.organizacao.autorizacao import filtrar_escopo
from .forms import QuadroSemanalForm
from .services import montar_quadro_semanal


@login_required
@require_GET
def quadro_semanal(request):
    parametros = request.GET.copy()
    parametros.setdefault("semana", timezone.localdate().isoformat())
    form = QuadroSemanalForm(parametros, ator=request.user)
    contexto = {"form": form, **navegacao_operacional(request.user)}
    if not form.is_valid():
        return render(request, "planejamento/quadro_semanal.html", contexto, status=400)
    dados = form.cleaned_data
    setor_id = dados["setor"].pk if dados["setor"] else None
    quadro = montar_quadro_semanal(ator=request.user, semana=dados["semana"],
                                  setor_id=setor_id, fim_semana=dados["fim_semana"])
    contexto.update(quadro)
    if not quadro['linhas']:
        contexto['orientacao'] = proximo_passo(request.user, setor_id=setor_id, semana=dados['semana'])
        todos = filtrar_escopo(request.user, Alocacao.objects.all())
        contexto['semana_tem_outro_setor'] = bool(setor_id and todos.filter(
            data__range=(quadro['inicio'], quadro['fim'])).exists())
    for direcao in ("anterior", "proxima"):
        dia = quadro[direcao]
        consulta = {"semana": dia.isoformat()} if dia else None
        if consulta is not None:
            if setor_id is not None:
                consulta["setor"] = setor_id
            if dados["fim_semana"]:
                consulta["fim_semana"] = "on"
        contexto[f"url_{direcao}"] = f"?{urlencode(consulta)}" if consulta is not None else None
    return render(request, "planejamento/quadro_semanal.html", contexto)
