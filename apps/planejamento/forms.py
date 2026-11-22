from datetime import timedelta

from django import forms
from django.conf import settings

from apps.organizacao.models import Funcao, Trabalhador, Turno
from .models import Tarefa
from .services import setores_permitidos, semana_de
from apps.organizacao.autorizacao import filtrar_escopo


class TrabalhadorTurnoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        if not settings.OP_APP_TURNOS_ENABLED:
            return str(obj)
        return f"{obj.nome} — {obj._turno_vigente or 'Turno não informado'}"


class AlocacaoMultidiaForm(forms.Form):
    turno = forms.ModelChoiceField(label='Turno', queryset=Turno.objects.filter(ativo=True))
    trabalhador = TrabalhadorTurnoChoiceField(queryset=Trabalhador.objects.filter(ativo=True)
                                         .select_related("setor_principal", "funcao_principal"))
    tarefa = forms.ModelChoiceField(queryset=Tarefa.objects.filter(
        status__in=(Tarefa.Status.PENDENTE, Tarefa.Status.EM_ANDAMENTO)))
    inicio = forms.DateField(label="Primeiro dia", widget=forms.DateInput(attrs={"type": "date"}))
    fim = forms.DateField(label="Último dia", widget=forms.DateInput(attrs={"type": "date"}))
    dias_semana = forms.MultipleChoiceField(
        label="Dias da semana", choices=list(enumerate(("Segunda", "Terça", "Quarta", "Quinta",
                                                       "Sexta", "Sábado", "Domingo"))),
        initial=[0, 1, 2, 3, 4], widget=forms.CheckboxSelectMultiple,
    )
    observacao = forms.CharField(label="Observação", required=False, widget=forms.Textarea)

    def __init__(self, *args, ator=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.OP_APP_TURNOS_ENABLED:
            self.fields.pop('turno')
        referencia = None
        try:
            referencia = forms.DateField().clean(self.data.get('inicio') or self.initial.get('inicio'))
        except forms.ValidationError:
            pass
        for campo in ("trabalhador", "tarefa"):
            self.fields[campo].queryset = filtrar_escopo(ator, self.fields[campo].queryset,
                data_referencia=referencia if campo == 'trabalhador' else None)
        self.fields['tarefa'].queryset = self.fields['tarefa'].queryset.prefetch_related('atividades')
        self.fields['tarefa'].widget = TarefaPeriodoSelect(choices=self.fields['tarefa'].choices)
        if settings.OP_APP_TURNOS_ENABLED:
            self.fields['trabalhador'].widget.attrs['data-turno-referencia'] = 'inicio'
            self.fields['trabalhador'].help_text = 'Turno habitual no primeiro dia informado; sem data, considera hoje.'
            from apps.organizacao.autorizacao import turnos_permitidos, setores_do_usuario
            permitidos = set()
            for setor in setores_do_usuario(ator):
                permitidos |= turnos_permitidos(ator, setor.pk)
            self.fields['turno'].queryset = Turno.objects.filter(ativo=True, pk__in=permitidos)

    class Media:
        js = ('planejamento/js/turno_trabalhador.js', 'planejamento/js/tarefa_atividades.js')

    def clean(self):
        dados = super().clean()
        inicio, fim = dados.get("inicio"), dados.get("fim")
        if inicio and fim:
            if fim < inicio:
                self.add_error("fim", "O último dia não pode anteceder o primeiro.")
            elif (fim - inicio).days > 365:
                self.add_error("fim", "Selecione até 366 dias por operação.")
            elif dados.get("dias_semana"):
                dias = {int(dia) for dia in dados["dias_semana"]}
                datas = [inicio + timedelta(days=i) for i in range((fim-inicio).days + 1)
                         if (inicio + timedelta(days=i)).weekday() in dias]
                if not datas:
                    self.add_error("dias_semana", "Nenhum dia selecionado pertence ao período.")
                dados["datas"] = datas
        return dados


class QuadroSemanalForm(forms.Form):
    semana = forms.DateField(label='Data da semana', widget=forms.DateInput(attrs={'type':'date'}))
    setor = forms.ModelChoiceField(label='Setor', queryset=None, required=False,
                                  empty_label='Todos os setores permitidos',
                                  error_messages={'invalid_choice':'Selecione um setor permitido.'})
    turno = forms.ChoiceField(label='Turno', required=False)
    trabalhador = forms.ModelChoiceField(label='Trabalhador', queryset=Trabalhador.objects.none(), required=False,
                                        empty_label='Todos os trabalhadores permitidos')
    tarefa = forms.ModelChoiceField(label='Tarefa', queryset=Tarefa.objects.none(), required=False,
                                   empty_label='Todas as tarefas permitidas')
    dia = forms.TypedChoiceField(label='Dia da semana', required=False, coerce=int, empty_value=None,
        choices=[('', 'Semana completa'), *enumerate(('Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'))])
    status = forms.ChoiceField(label='Status atual da tarefa', required=False,
                              choices=[('', 'Todos os estados'), *Tarefa.Status.choices])
    fim_semana = forms.BooleanField(label='Mostrar sábado e domingo', required=False)

    def __init__(self, *args, ator, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q
        from .models import Alocacao
        from apps.organizacao.autorizacao import turnos_permitidos
        self.fields['setor'].queryset = setores_permitidos(ator)
        visiveis = filtrar_escopo(ator, Alocacao.objects.all())
        atuais = filtrar_escopo(ator, Trabalhador.objects.all())
        self.fields['trabalhador'].queryset = Trabalhador.objects.filter(
            Q(pk__in=atuais.values('pk')) | Q(pk__in=visiveis.values('trabalhador_id')))
        self.fields['tarefa'].queryset = filtrar_escopo(ator, Tarefa.objects.all())
        if settings.OP_APP_TURNOS_ENABLED:
            codigos = set()
            for setor in self.fields['setor'].queryset:
                codigos |= turnos_permitidos(ator, setor.pk)
            opcoes = [(c,c) for c in sorted(codigos)]
            if visiveis.filter(turno__isnull=True).exists():
                opcoes.append(('nao_informado', 'Turno não informado'))
            self.fields['turno'].choices = [('', 'Todos os turnos permitidos'), *opcoes]
        else:
            self.fields.pop('turno')

    def clean_semana(self):
        dia = self.cleaned_data['semana']
        semana_de(dia)
        return dia


class AtividadesWidget(forms.CheckboxSelectMultiple):
    template_name = 'planejamento/widgets/atividades.html'


class TarefaTurnosForm(forms.ModelForm):
    atividades_da_tarefa = forms.ModelMultipleChoiceField(label='Atividades da tarefa', queryset=Funcao.objects.all(),
        widget=AtividadesWidget, help_text='Trabalhos necessários à tarefa, combinados para a equipe; não são competências individuais.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and 'atividades_da_tarefa' in self.fields:
            self.initial['atividades_da_tarefa'] = list(self.instance.atividades.values_list('pk', flat=True))
        if not settings.OP_APP_TURNOS_ENABLED:
            self.fields.pop('turno_operacao', None)
            self.fields.pop('observacao_turno', None)

    def _save_m2m(self):
        # O conjunto é gravado atomicamente por Tarefa.save(), com autorização e histórico.
        pass

    turno_operacao = forms.ModelChoiceField(label='Turno desta operação', queryset=Turno.objects.filter(ativo=True), required=False)
    observacao_turno = forms.CharField(label='Acrescentar observação do turno', required=False, widget=forms.Textarea)

    class Meta:
        model = Tarefa
        fields = '__all__'


class TrabalhadoresTurnoChoiceField(forms.ModelMultipleChoiceField):
    label_from_instance = TrabalhadorTurnoChoiceField.label_from_instance


class TarefaPeriodoSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value and hasattr(value, 'instance'):
            tarefa = value.instance
            option['attrs']['data-inicio'] = tarefa.inicio_previsto.isoformat()
            option['attrs']['data-fim'] = tarefa.fim_previsto.isoformat()
            option['attrs']['data-atividades'] = tarefa.atividades_descricao
            option['label'] = f'{label} — {tarefa.inicio_previsto:%d/%m/%Y} a {tarefa.fim_previsto:%d/%m/%Y}'
        return option


class PlanejarForm(AlocacaoMultidiaForm):
    trabalhadores = TrabalhadoresTurnoChoiceField(
        label='Trabalhadores', queryset=Trabalhador.objects.none(),
        widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tarefa'].widget = TarefaPeriodoSelect(choices=self.fields['tarefa'].choices)
        self.fields['tarefa'].help_text = 'Atividades são definidas na tarefa. As alocações devem estar dentro do período previsto.'
        anterior = self.fields.pop('trabalhador')
        campo = self.fields['trabalhadores']
        campo.queryset = anterior.queryset
        campo.help_text = 'Selecione uma ou mais pessoas. ' + str(anterior.help_text)
        if settings.OP_APP_TURNOS_ENABLED:
            campo.widget.attrs['data-turno-referencia'] = 'inicio'
        self.order_fields(['tarefa', 'inicio', 'fim', 'dias_semana', 'turno', 'trabalhadores', 'observacao'])

    class Media:
        extend = False
        js = ('planejamento/js/planejar.js',)

    def clean(self):
        dados = super().clean()
        tarefa = dados.get('tarefa')
        if tarefa and dados.get('datas') and any(
                not tarefa.inicio_previsto <= dia <= tarefa.fim_previsto for dia in dados['datas']):
            raise forms.ValidationError(
                f'As datas selecionadas devem estar no período previsto da tarefa: '
                f'{tarefa.inicio_previsto:%d/%m/%Y} a {tarefa.fim_previsto:%d/%m/%Y}.')
        if dados.get('trabalhadores') is not None and dados.get('datas'):
            if len(dados['trabalhadores']) * len(dados['datas']) > 1000:
                raise forms.ValidationError('Selecione no máximo 1.000 alocações por confirmação.')
        return dados
