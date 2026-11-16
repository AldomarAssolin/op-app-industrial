from datetime import timedelta

from django import forms

from apps.organizacao.models import Funcao, Trabalhador
from .models import Tarefa
from .services import setores_permitidos, semana_de


class AlocacaoMultidiaForm(forms.Form):
    trabalhador = forms.ModelChoiceField(queryset=Trabalhador.objects.filter(ativo=True)
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
