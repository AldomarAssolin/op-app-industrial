from urllib.parse import urlencode
from django.http import QueryDict
from django.urls import reverse
from .forms import QuadroSemanalForm
from apps.organizacao.turnos import data_operacional_hoje


def contexto_quadro(ator, consulta, *, semana=None):
    params = QueryDict(consulta, mutable=True) if isinstance(consulta, str) else consulta.copy()
    params.setdefault('semana', str(semana or data_operacional_hoje()))
    form = QuadroSemanalForm(params, ator=ator)
    if not form.is_valid():
        return urlencode({'semana':str(semana or data_operacional_hoje())})
    dados = form.cleaned_data
    retorno = {'semana':dados['semana'].isoformat()}
    for chave in ('setor','trabalhador','tarefa','turno','status','dia','fim_semana'):
        valor = dados.get(chave)
        if valor is not None and valor != '' and valor is not False:
            retorno[chave] = 'on' if chave == 'fim_semana' else getattr(valor, 'pk', valor)
    return urlencode(retorno)


def url_quadro(contexto):
    return reverse('planejamento:quadro_semanal') + '?' + contexto
