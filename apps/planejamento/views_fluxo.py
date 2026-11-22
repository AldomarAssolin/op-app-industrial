from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from apps.organizacao.autorizacao import exigir_operacao
from .forms import PlanejarForm
from .fluxo import revisar_planejamento, confirmar_planejamento, carregar_token
from .contexto import contexto_quadro, url_quadro
from .views_operacionais import navegacao_operacional


@login_required
@require_http_methods(['GET','POST'])
def planejar(request):
    exigir_operacao(request.user, 'planejamento.add_alocacao')
    contexto = contexto_quadro(request.user, request.POST.get('retorno', '') if request.method == 'POST' else request.GET)
    revisao = None
    initial = {k:request.GET[k] for k in ('tarefa','inicio','fim','turno') if k in request.GET}
    if request.method == 'POST' and request.POST.get('confirmacao'):
        token = request.POST['confirmacao']
        try:
            dados_token = carregar_token(token, request.user)
            if not request.POST.get('retorno'):
                contexto = contexto_quadro(request.user, '', semana=date.fromisoformat(dados_token['payload']['datas'][0]))
            recibo, novo = confirmar_planejamento(ator=request.user, token=token)
        except ValidationError as erro:
            try:
                payload = carregar_token(token, request.user)['payload']
                datas = sorted(payload['datas'])
                initial = {'tarefa':payload['tarefa'], 'trabalhadores':payload['trabalhadores'],
                    'inicio':datas[0], 'fim':datas[-1], 'dias_semana':sorted({date.fromisoformat(d).weekday() for d in datas}),
                    'turno':payload['turno'], 'funcao_desempenhada':payload['funcao'], 'observacao':payload['observacao']}
            except (ValidationError, KeyError, IndexError, ValueError, TypeError):
                initial = {}
            form = PlanejarForm(initial or {}, ator=request.user)
            form.is_valid()
            form.add_error(None, ' '.join(erro.messages))
        else:
            messages.success(request, f'{recibo.quantidade} alocações confirmadas.' if novo else 'Este planejamento já foi confirmado; nenhuma alocação foi duplicada.')
            return redirect(url_quadro(contexto))
    else:
        form = PlanejarForm(request.POST or None, ator=request.user, initial=initial)
        if request.method == 'POST' and form.is_valid():
            try:
                revisao = revisar_planejamento(ator=request.user, dados=form.cleaned_data)
                if not request.POST.get('retorno'):
                    contexto = contexto_quadro(request.user, '', semana=form.cleaned_data['inicio'])
            except ValidationError as erro:
                form.add_error(None, ' '.join(erro.messages))
    return render(request, 'planejamento/operacional/planejar.html', {
        **navegacao_operacional(request.user), 'form':form, 'revisao':revisao,
        'retorno':contexto if revisao or request.POST.get('retorno') or request.GET.get('semana') else '', 'voltar':url_quadro(contexto)})
