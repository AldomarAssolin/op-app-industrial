from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Alocacao, exigir_permissao


@transaction.atomic
def alocar_dias(*, ator, trabalhador, tarefa, datas, funcao_desempenhada, observacao=""):
    """Cria todos os dias ou nenhum; repetição exata é erro, não sobrescrita."""
    exigir_permissao(ator, "add")
    dias = list(datas)
    if not dias or any(type(dia) is not date for dia in dias):
        raise ValidationError("Informe uma ou mais datas válidas.")
    if len(set(dias)) != len(dias):
        raise ValidationError("A seleção contém datas repetidas.")
    registros = []
    for dia in sorted(dias):
        alocacao = Alocacao(trabalhador=trabalhador, tarefa=tarefa, data=dia,
                            funcao_desempenhada=funcao_desempenhada, observacao=observacao)
        alocacao.save(ator=ator)
        registros.append(alocacao)
    return registros


def consultar_alocacoes(*, ator, inicio, fim, setor_id=None):
    exigir_permissao(ator, "view")
    if type(inicio) is not date or type(fim) is not date or fim < inicio:
        raise ValidationError("Informe um período de consulta válido.")
    consulta = Alocacao.objects.select_related(
        "trabalhador", "tarefa", "tarefa__setor", "funcao_desempenhada",
        "criado_por", "alterado_por",
    ).filter(data__range=(inicio, fim))
    if setor_id is not None:
        consulta = consulta.filter(tarefa__setor_id=setor_id)
    return consulta
