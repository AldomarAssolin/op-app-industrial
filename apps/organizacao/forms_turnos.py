from django import forms
from .models import Turno


class TrocaTurnoForm(forms.Form):
    classificar_legado = forms.BooleanField(required=False, label='Classificar também as alocações futuras sem turno, após revisar a lista')
    turno = forms.ModelChoiceField(label='Novo turno habitual', queryset=Turno.objects.filter(ativo=True))
    vigencia = forms.DateField(label='Data operacional de vigência', widget=forms.DateInput(attrs={'type': 'date'}))
