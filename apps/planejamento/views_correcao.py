from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from apps.organizacao.autorizacao import exigir_operacao, filtrar_escopo, ator_atual
from apps.organizacao.models import Trabalhador, Funcao
from .models import Alocacao, Tarefa
from .forms import TrabalhadorTurnoChoiceField
from .views_operacionais import navegacao_operacional
from .contexto import contexto_quadro, url_quadro


class CorrecaoForm(forms.ModelForm):
    tarefa = forms.ModelChoiceField(label='Tarefa (mantida nesta correção)', queryset=Tarefa.objects.none(), disabled=True)
    versao = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Alocacao
        fields = ('tarefa','trabalhador','data','observacao')
        widgets = {'data':forms.DateInput(attrs={'type':'date'}, format='%Y-%m-%d')}
        field_classes = {'trabalhador':TrabalhadorTurnoChoiceField}

    class Media:
        js = ('planejamento/js/turno_trabalhador.js',)

    def __init__(self, *args, ator, **kwargs):
        super().__init__(*args, **kwargs)
        # Campo desabilitado recebe erros do modelo sem permitir troca por POST.
        self.fields['tarefa'].queryset = Tarefa.objects.filter(pk=self.instance.tarefa_id)
        try:
            dia = forms.DateField().clean(self.data.get('data') or self.initial.get('data'))
        except forms.ValidationError:
            dia = self.instance.data
        self.fields['trabalhador'].queryset = filtrar_escopo(ator, Trabalhador.objects.filter(ativo=True), data_referencia=dia)
        from django.conf import settings
        if settings.OP_APP_TURNOS_ENABLED:
            self.fields['trabalhador'].widget.attrs['data-turno-referencia'] = 'data'


def _versao(obj, ator):
    return signing.dumps({'pk':obj.pk, 'ator':ator.pk, 'alterado':obj.alterado_em.isoformat()}, salt='correcao-alocacao')


@transaction.atomic
def _gravar(ator, obj, token, *, remover=False):
    from django.contrib.auth import get_user_model
    ator = ator_atual(ator)
    exigir_operacao(ator, 'planejamento.delete_alocacao' if remover else 'planejamento.change_alocacao')
    ator = get_user_model().objects.select_for_update().filter(pk=ator.pk).first()
    exigir_operacao(ator, 'planejamento.delete_alocacao' if remover else 'planejamento.change_alocacao')
    try:
        versao = signing.loads(token, salt='correcao-alocacao', max_age=1800)
    except signing.BadSignature as erro:
        raise ValidationError('A edição expirou ou foi alterada. Recarregue e confira novamente.') from erro
    anterior = get_object_or_404(Alocacao.objects.all(), pk=obj.pk)
    if versao != {'pk':anterior.pk, 'ator':ator.pk, 'alterado':anterior.alterado_em.isoformat()}:
        raise ValidationError('A alocação mudou após abrir a página. Recarregue e confira novamente.')
    list(Tarefa.objects.select_for_update().filter(pk=anterior.tarefa_id))
    list(Trabalhador.objects.select_for_update().filter(pk__in={anterior.trabalhador_id,obj.trabalhador_id}).order_by('pk'))
    atual = get_object_or_404(filtrar_escopo(ator, Alocacao.objects.select_for_update()), pk=obj.pk)
    if versao != {'pk':atual.pk, 'ator':ator.pk, 'alterado':atual.alterado_em.isoformat()}:
        raise ValidationError('A alocação mudou após abrir a página. Recarregue e confira novamente.')
    if remover:
        atual.delete(ator=ator)
    else:
        obj.save(ator=ator)


@login_required
@require_http_methods(['GET','POST'])
def corrigir_alocacao(request, pk):
    exigir_operacao(request.user, 'planejamento.change_alocacao')
    obj = get_object_or_404(filtrar_escopo(request.user, Alocacao.objects.all()), pk=pk)
    contexto = contexto_quadro(request.user, request.POST.get('retorno', '') if request.method=='POST' else request.GET.get('retorno',''), semana=obj.data)
    form = CorrecaoForm(request.POST or None, instance=obj, ator=request.user, initial={'versao':_versao(obj,request.user), 'data':request.GET.get('data') or obj.data})
    if request.method=='POST' and form.is_valid():
        try:
            _gravar(request.user, form.save(commit=False), form.cleaned_data['versao'])
        except ValidationError as erro:
            form.add_error(None, ' '.join(erro.messages))
        else:
            messages.success(request, 'Alocação atualizada. Os demais dias foram preservados.')
            return redirect(url_quadro(contexto))
    return render(request, 'planejamento/operacional/corrigir.html', {**navegacao_operacional(request.user),
        'form':form, 'alocacao':obj, 'retorno':contexto, 'voltar':url_quadro(contexto)})


@login_required
@require_http_methods(['GET','POST'])
def remover_alocacao(request, pk):
    exigir_operacao(request.user, 'planejamento.delete_alocacao')
    obj = get_object_or_404(filtrar_escopo(request.user, Alocacao.objects.all()), pk=pk)
    contexto = contexto_quadro(request.user, request.POST.get('retorno','') if request.method=='POST' else request.GET.get('retorno',''), semana=obj.data)
    erro = None
    if request.method=='POST':
        try:
            _gravar(request.user,obj,request.POST.get('versao',''),remover=True)
        except ValidationError as exc:
            erro = ' '.join(exc.messages)
        else:
            messages.success(request,'Alocação removida. Os demais dias foram preservados.')
            return redirect(url_quadro(contexto))
    return render(request,'planejamento/operacional/remover.html',{**navegacao_operacional(request.user),
        'alocacao':obj,'versao':_versao(obj,request.user),'erro':erro,'retorno':contexto,'voltar':url_quadro(contexto)})
