from django import forms
from .models import Turno, Trabalhador


class TrocaTurnoForm(forms.Form):
    classificar_legado = forms.BooleanField(required=False, label='Classificar também as alocações futuras sem turno, após revisar a lista')
    turno = forms.ModelChoiceField(label='Novo turno habitual', queryset=Turno.objects.filter(ativo=True))
    vigencia = forms.DateField(label='Data operacional de vigência', widget=forms.DateInput(attrs={'type': 'date'}))


class TrabalhadorCadastroForm(forms.ModelForm):
    turno_inicial = forms.ModelChoiceField(
        label='Turno inicial', queryset=Turno.objects.filter(ativo=True), required=False,
        empty_label='Turno não informado',
        help_text='Opcional. Quando informado, vale a partir de hoje e registra o histórico.')

    class Meta:
        model = Trabalhador
        fields = '__all__'
