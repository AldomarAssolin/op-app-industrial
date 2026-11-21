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
    funcao_desempenhada = forms.ModelChoiceField(label="Função desempenhada",
                                                queryset=Funcao.objects.all())
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
        if settings.OP_APP_TURNOS_ENABLED:
            self.fields['trabalhador'].widget.attrs['data-turno-referencia'] = 'inicio'
            self.fields['trabalhador'].help_text = 'Turno habitual no primeiro dia informado; sem data, considera hoje.'
            from apps.organizacao.autorizacao import turnos_permitidos, setores_do_usuario
            permitidos = set()
            for setor in setores_do_usuario(ator):
                permitidos |= turnos_permitidos(ator, setor.pk)
            self.fields['turno'].queryset = Turno.objects.filter(ativo=True, pk__in=permitidos)

    class Media:
        js = ('planejamento/js/turno_trabalhador.js',)

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
    semana = forms.DateField(label="Data da semana", widget=forms.DateInput(attrs={"type": "date"}))
    setor = forms.ModelChoiceField(label="Setor", queryset=None, required=False,
                                  empty_label="Todos os setores permitidos",
                                  error_messages={"invalid_choice": "Selecione um setor permitido."})
    fim_semana = forms.BooleanField(label="Mostrar sábado e domingo", required=False)

    def __init__(self, *args, ator, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["setor"].queryset = setores_permitidos(ator)

    def clean_semana(self):
        dia = self.cleaned_data["semana"]
        semana_de(dia)
        return dia


class TarefaTurnosForm(forms.ModelForm):
    turno_operacao = forms.ModelChoiceField(label='Turno desta operação', queryset=Turno.objects.filter(ativo=True), required=False)
    observacao_turno = forms.CharField(label='Acrescentar observação do turno', required=False, widget=forms.Textarea)

    class Meta:
        model = Tarefa
        fields = '__all__'
