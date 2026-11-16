from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .models import Alocacao, exigir_permissao
from apps.organizacao.models import Setor


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
    permitidos = setores_permitidos(ator)
    consulta = consulta.filter(tarefa__setor__in=permitidos)
    if setor_id is not None:
        if not permitidos.filter(pk=setor_id).exists():
            raise PermissionDenied("Setor não autorizado para consulta.")
        consulta = consulta.filter(tarefa__setor_id=setor_id)
    return consulta


def setores_permitidos(ator):
    exigir_permissao(ator, "view")
    setores = Setor.objects.all()
    if not ator.is_superuser:
        setores = setores.filter(acessos_usuarios__usuario=ator)
    return setores


def semana_de(dia):
    if type(dia) is not date:
        raise ValidationError("Informe uma data válida para a semana.")
    inicio = dia - timedelta(days=dia.weekday())
    try:
        fim = inicio + timedelta(days=6)
    except OverflowError:
        raise ValidationError("Selecione uma semana completa dentro do calendário.")
    return inicio, fim


def montar_quadro_semanal(*, ator, semana, setor_id=None, fim_semana=False):
    inicio, fim = semana_de(semana)
    alocacoes = list(consultar_alocacoes(ator=ator, inicio=inicio, fim=fim, setor_id=setor_id)
                     .order_by("trabalhador__nome", "trabalhador_id", "tarefa__titulo", "tarefa_id",
                               "funcao_desempenhada__nome", "funcao_desempenhada_id", "data"))
    mostrar_fim_semana = fim_semana or any(a.data.weekday() >= 5 for a in alocacoes)
    dias = [inicio + timedelta(days=i) for i in range(7 if mostrar_fim_semana else 5)]
    grupos = {}
    for alocacao in alocacoes:
        chave = (alocacao.trabalhador_id, alocacao.funcao_desempenhada_id, alocacao.tarefa_id)
        if chave not in grupos:
            grupos[chave] = {"trabalhador": alocacao.trabalhador,
                             "funcao": alocacao.funcao_desempenhada, "tarefa": alocacao.tarefa,
                             "por_data": {}}
        grupos[chave]["por_data"][alocacao.data] = alocacao
    linhas = []
    for grupo in grupos.values():
        por_data = grupo.pop("por_data")
        grupo["celulas"] = [{"data": dia, "alocacao": por_data.get(dia)} for dia in dias]
        linhas.append(grupo)
    nomes = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
    return {"inicio": inicio, "fim": fim, "dias": dias, "linhas": linhas,
            "colunas": [{"data": dia, "nome": nomes[dia.weekday()]} for dia in dias],
            "mostrar_fim_semana": mostrar_fim_semana,
            "anterior": inicio-timedelta(days=7) if inicio >= date.min+timedelta(days=7) else None,
            "proxima": inicio+timedelta(days=7) if inicio <= date.max-timedelta(days=13) else None}
