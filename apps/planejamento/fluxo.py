"""Revisão assinada e confirmação atômica do planejamento operacional."""
from datetime import date
import hashlib
import json
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.organizacao.autorizacao import exigir_operacao, exigir_escopo_objeto, filtrar_escopo, ator_atual
from apps.organizacao.models import Trabalhador, Funcao, Turno
from .models import Alocacao, Tarefa, ConfirmacaoPlanejamento

SALT = 'planejamento-operacional-v1'


def carregar_token(token, ator):
    try:
        dados = signing.loads(token, salt=SALT, max_age=1800)
        if dados['ator'] != ator.pk or dados['turnos'] != settings.OP_APP_TURNOS_ENABLED:
            raise signing.BadSignature()
        return dados
    except (signing.BadSignature, KeyError, TypeError, ValueError) as erro:
        raise ValidationError('Revisão inválida ou expirada. Revise o planejamento novamente.') from erro


def _revisar(ator, payload):
    ator = ator_atual(ator)
    exigir_operacao(ator, 'planejamento.add_alocacao')
    try:
        datas = [date.fromisoformat(d) for d in payload['datas']]
        ids = payload['trabalhadores']
        if (not datas or len(set(datas)) != len(datas) or not ids or len(set(ids)) != len(ids)
                or len(ids) * len(datas) > 1000):
            raise ValueError()
        tarefa = filtrar_escopo(ator, Tarefa.objects.all()).get(pk=payload['tarefa'])
        pessoas = list(Trabalhador.objects.filter(pk__in=ids).order_by('pk'))
        if len(pessoas) != len(ids):
            raise ValueError()
        atividades = list(tarefa.atividades.order_by('pk'))
        if not atividades:
            raise ValidationError('Cadastre as atividades na tarefa antes de planejar a equipe.')
        turno = Turno.objects.get(pk=payload['turno'], ativo=True) if payload['turno'] else None
    except (ValueError, TypeError, KeyError, Tarefa.DoesNotExist, Funcao.DoesNotExist, Turno.DoesNotExist) as erro:
        raise ValidationError('A seleção não está mais disponível. Confira os campos e revise novamente.') from erro
    linhas = []
    snapshot = [tarefa.pk, tarefa.titulo, tarefa.setor_id, tarefa.status,
                str(tarefa.inicio_previsto), str(tarefa.fim_previsto),
                turno.pk if turno else None, [(a.pk, a.nome) for a in atividades]]
    for pessoa in pessoas:
        snapshot.append([pessoa.pk, pessoa.nome, pessoa.setor_principal_id, pessoa.ativo,
                         list(pessoa.mudancas_turno.order_by('pk').values_list('pk', 'vigencia', 'turno_novo_id'))])
        for dia in sorted(datas):
            obj = Alocacao(trabalhador=pessoa, tarefa=tarefa, data=dia, turno=turno,
                           observacao=payload['observacao'],
                           criado_por=ator, alterado_por=ator)
            # Checar escopo antes de qualquer mensagem com nome de pessoa.
            exigir_escopo_objeto(ator, obj)
            try:
                if settings.OP_APP_TURNOS_ENABLED:
                    habitual = pessoa.turno_em(dia)
                    if not turno or not habitual or habitual.pk != turno.pk:
                        raise ValidationError('Turno diferente do habitual vigente; procure o Coordenador.')
                    if Alocacao.objects.filter(trabalhador=pessoa, data=dia).exclude(turno=turno).exists():
                        raise ValidationError('Há planejamento em outro turno ou sem classificação; procure o Coordenador.')
                obj.full_clean()
            except ValidationError as erro:
                raise ValidationError(f'{pessoa.nome} · {dia:%d/%m/%Y}: ' + ' '.join(erro.messages)) from erro
            linhas.append(obj)
    resumo = hashlib.sha256(json.dumps(snapshot, default=str, sort_keys=True).encode()).hexdigest()
    return {'linhas':linhas, 'resumo':resumo, 'tarefa':tarefa, 'pessoas':pessoas, 'atividades':atividades, 'turno':turno}


def revisar_planejamento(*, ator, dados):
    payload = {'tarefa':dados['tarefa'].pk,
               'trabalhadores':sorted(p.pk for p in dados['trabalhadores']),
               'datas':sorted(d.isoformat() for d in dados['datas']),
               'turno':dados.get('turno').pk if dados.get('turno') else None,
               'observacao':dados.get('observacao', '')}
    revisao = _revisar(ator, payload)
    revisao['token'] = signing.dumps({'ator':ator.pk, 'turnos':settings.OP_APP_TURNOS_ENABLED,
        'lote':str(uuid4()), 'payload':payload, 'resumo':revisao['resumo']}, salt=SALT, compress=True)
    return revisao


@transaction.atomic
def confirmar_planejamento(*, ator, token):
    from django.contrib.auth import get_user_model
    ator = ator_atual(ator)
    exigir_operacao(ator, 'planejamento.add_alocacao')
    # Conta e permissões frescas, inclusive sem a feature de turnos.
    ator = get_user_model().objects.select_for_update().filter(pk=ator.pk).first()
    exigir_operacao(ator, 'planejamento.add_alocacao')
    dados = carregar_token(token, ator)
    digest = hashlib.sha256(token.encode()).hexdigest()
    anterior = ConfirmacaoPlanejamento.objects.filter(pk=dados['lote'], registrado_por=ator).first()
    if anterior:
        if anterior.resumo != digest:
            raise ValidationError('Confirmação incompatível. Revise novamente.')
        return anterior, False
    payload = dados['payload']
    list(Tarefa.objects.select_for_update().filter(pk=payload['tarefa']))
    list(Trabalhador.objects.select_for_update().filter(pk__in=payload['trabalhadores']).order_by('pk'))
    revisao = _revisar(ator, payload)
    if revisao['resumo'] != dados['resumo']:
        raise ValidationError('Os dados mudaram depois da revisão. Confira e revise novamente.')
    for linha in revisao['linhas']:
        linha.save(ator=ator)
    recibo = ConfirmacaoPlanejamento.objects.create(id=dados['lote'], registrado_por=ator,
        resumo=digest, quantidade=len(revisao['linhas']))
    return recibo, True
