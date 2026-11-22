from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .models import Alocacao, exigir_permissao
from apps.organizacao.models import Setor
from apps.organizacao.autorizacao import setores_do_usuario, filtrar_escopo, travar_autorizacao


@transaction.atomic
def alocar_dias(*, ator, trabalhador, tarefa, datas, funcao_desempenhada, observacao="", turno=None):
    """Cria todos os dias ou nenhum; repetição exata é erro, não sobrescrita."""
    ator = travar_autorizacao(ator)
    exigir_permissao(ator, "add")
    dias = list(datas)
    if not dias or any(type(dia) is not date for dia in dias):
        raise ValidationError("Informe uma ou mais datas válidas.")
    if len(set(dias)) != len(dias):
        raise ValidationError("A seleção contém datas repetidas.")
    registros = []
    for dia in sorted(dias):
        alocacao = Alocacao(trabalhador=trabalhador, tarefa=tarefa, data=dia,
                            funcao_desempenhada=funcao_desempenhada, observacao=observacao, turno=turno)
        alocacao.save(ator=ator)
        registros.append(alocacao)
    return registros


def consultar_alocacoes(*, ator, inicio, fim, setor_id=None):
    exigir_permissao(ator, "view")
    if type(inicio) is not date or type(fim) is not date or fim < inicio:
        raise ValidationError("Informe um período de consulta válido.")
    consulta = Alocacao.objects.select_related(
        "trabalhador", "tarefa", "tarefa__setor", "funcao_desempenhada", "turno",
        "criado_por", "alterado_por",
    ).filter(data__range=(inicio, fim))
    permitidos = setores_permitidos(ator)
    consulta = filtrar_escopo(ator, consulta)
    if setor_id is not None:
        if not permitidos.filter(pk=setor_id).exists():
            raise PermissionDenied("Setor não autorizado para consulta.")
        consulta = consulta.filter(tarefa__setor_id=setor_id)
    return consulta


def setores_permitidos(ator):
    exigir_permissao(ator, "view")
    return setores_do_usuario(ator)


def semana_de(dia):
    if type(dia) is not date:
        raise ValidationError("Informe uma data válida para a semana.")
    inicio = dia - timedelta(days=dia.weekday())
    try:
        fim = inicio + timedelta(days=6)
    except OverflowError:
        raise ValidationError("Selecione uma semana completa dentro do calendário.")
    return inicio, fim


def montar_quadro_semanal(*, ator, semana, setor_id=None, fim_semana=False,
                         turno=None, trabalhador_id=None, tarefa_id=None, status=None, dia=None):
    inicio, fim = semana_de(semana)
    consulta = consultar_alocacoes(ator=ator, inicio=inicio, fim=fim, setor_id=setor_id)
    # A mesma validação de opções do formulário protege chamadas diretas do serviço.
    if any((turno, trabalhador_id, tarefa_id, status, dia is not None)):
        from .forms import QuadroSemanalForm
        validacao = QuadroSemanalForm({'semana':semana.isoformat(), 'setor':setor_id or '',
            'turno':turno or '', 'trabalhador':trabalhador_id or '', 'tarefa':tarefa_id or '',
            'status':status or '', 'dia':dia if dia is not None else ''}, ator=ator)
        if not validacao.is_valid():
            raise PermissionDenied('Filtro inválido ou fora do acesso autorizado.')
        dia = validacao.cleaned_data['dia']
    if turno:
        consulta = consulta.filter(turno__isnull=True) if turno == 'nao_informado' else consulta.filter(turno_id=turno)
    if trabalhador_id:
        consulta = consulta.filter(trabalhador_id=trabalhador_id)
    if tarefa_id:
        consulta = consulta.filter(tarefa_id=tarefa_id)
    if status:
        consulta = consulta.filter(tarefa__status=status)
    if dia is not None:
        consulta = consulta.filter(data=inicio + timedelta(days=dia))
    alocacoes = list(consulta.prefetch_related('atividades_adicionais').order_by('trabalhador__nome', 'trabalhador_id', 'tarefa__titulo',
                    'tarefa_id', 'funcao_desempenhada__nome', 'funcao_desempenhada_id', 'data'))
    mostrar_fim_semana = (dia >= 5) if dia is not None else (fim_semana or any(a.data.weekday() >= 5 for a in alocacoes))
    dias = [inicio + timedelta(days=dia)] if dia is not None else [inicio + timedelta(days=i) for i in range(7 if mostrar_fim_semana else 5)]
    grupos = {}
    for alocacao in alocacoes:
        chave = (alocacao.trabalhador_id, tuple(sorted(a.pk for a in alocacao.atividades_da_tarefa)), alocacao.tarefa_id, alocacao.turno_id)
        if chave not in grupos:
            grupos[chave] = {"trabalhador": alocacao.trabalhador,
                             "funcao": alocacao.funcao_desempenhada, "atividades": alocacao.atividades_descricao, "tarefa": alocacao.tarefa, "turno": alocacao.turno,
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
