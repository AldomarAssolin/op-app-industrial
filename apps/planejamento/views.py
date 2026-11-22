from urllib.parse import urlencode
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET
from .views_operacionais import navegacao_operacional
from .orientacao import proximo_passo, permite
from .models import Alocacao
from apps.organizacao.autorizacao import filtrar_escopo
from .forms import QuadroSemanalForm
from .services import montar_quadro_semanal
from .contexto import contexto_quadro


@login_required
@require_GET
def quadro_semanal(request):
    parametros = request.GET.copy()
    if settings.OP_APP_TURNOS_ENABLED:
        from apps.organizacao.turnos import data_operacional_hoje
        hoje = data_operacional_hoje()
    else:
        hoje = timezone.localdate()
    parametros.setdefault('semana', hoje.isoformat())
    form = QuadroSemanalForm(parametros, ator=request.user)
    contexto = {'turnos_habilitados':settings.OP_APP_TURNOS_ENABLED, 'form':form,
                **navegacao_operacional(request.user)}
    if not form.is_valid():
        return render(request, 'planejamento/quadro_semanal.html', contexto, status=400)
    dados = form.cleaned_data
    setor_id = dados['setor'].pk if dados['setor'] else None
    quadro = montar_quadro_semanal(ator=request.user, semana=dados['semana'], setor_id=setor_id,
        fim_semana=dados['fim_semana'], turno=dados.get('turno'),
        trabalhador_id=dados['trabalhador'].pk if dados['trabalhador'] else None,
        tarefa_id=dados['tarefa'].pk if dados['tarefa'] else None, status=dados['status'], dia=dados['dia'])
    contexto.update(quadro)
    retorno = contexto_quadro(request.user, parametros)
    contexto['url_planejar'] = reverse('planejamento:planejar') + '?' + retorno
    contexto['url_limpar'] = '?'+urlencode({'semana':dados['semana'].isoformat()})
    contexto['filtros_ativos'] = [{ 'nome':form.fields[k].label, 'valor':form[k].value(),
        'texto': str(dados[k]) if k in ('setor','trabalhador','tarefa') else dict(form.fields[k].choices).get(dados[k], dados[k])}
        for k in ('setor','turno','trabalhador','tarefa','dia','status') if k in dados and dados[k] is not None and dados[k] != '']
    contexto['pode_corrigir'] = permite(request.user, 'planejamento.change_alocacao')
    contexto['pode_remover'] = permite(request.user, 'planejamento.delete_alocacao')
    for linha in quadro['linhas']:
        for celula in linha['celulas']:
            if celula['alocacao']:
                for acao in ('corrigir','remover'):
                    celula['url_'+acao] = reverse('planejamento:'+acao+'_alocacao', args=[celula['alocacao'].pk])+'?'+urlencode({'retorno':retorno})
    if not quadro['linhas']:
        contexto['orientacao'] = proximo_passo(request.user, setor_id=setor_id, semana=dados['semana'])
        todos = filtrar_escopo(request.user, Alocacao.objects.all())
        contexto['semana_tem_outro_setor'] = bool(setor_id and todos.filter(data__range=(quadro['inicio'],quadro['fim'])).exists())
        contexto['semana_tem_registros'] = todos.filter(data__range=(quadro['inicio'],quadro['fim'])).exists()
        contexto['sem_acesso'] = not contexto['setores_permitidos']
    for direcao in ('anterior','proxima'):
        dia = quadro[direcao]
        consulta = parametros.copy()
        consulta['semana'] = dia.isoformat() if dia else ''
        # Só parâmetros reconhecidos e validados retornam à navegação.
        contexto['url_'+direcao] = '?'+contexto_quadro(request.user, consulta) if dia else None
    return render(request, 'planejamento/quadro_semanal.html', contexto)
