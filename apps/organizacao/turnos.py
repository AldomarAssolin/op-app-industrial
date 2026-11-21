"""Troca por vigência: revisão assinada, revalidação e confirmação atômica."""
from datetime import date
import hashlib
import json
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .autorizacao import COORDENADOR, exigir_operacao, exigir_setores, coordenador_no_setor, travar_autorizacao
from .models import MudancaTurno, Trabalhador, Turno


def data_operacional_hoje():
    # Referência de calendário da operação brasileira; não determina o turno pelo relógio.
    return timezone.localdate(timezone=ZoneInfo('America/Sao_Paulo'))


def exigir_coordenador(ator, setor_id=None):
    if not settings.OP_APP_TURNOS_ENABLED:
        raise PermissionDenied('A operação com turnos ainda não está habilitada.')
    from django.contrib.auth import get_user_model
    if not ator or not ator.is_authenticated:
        raise PermissionDenied('Operação não autorizada.')
    atual = get_user_model().objects.filter(pk=ator.pk).first()
    if atual is None:
        raise PermissionDenied('Operação não autorizada.')
    exigir_operacao(atual, 'organizacao.change_trabalhador')
    if not atual.is_superuser and not atual.groups.filter(name=COORDENADOR).exists():
        raise PermissionDenied('A troca de turno é responsabilidade do Coordenador.')
    if setor_id is not None and not atual.is_superuser and not coordenador_no_setor(atual, setor_id):
        raise PermissionDenied('A troca exige o Coordenador responsável pelo setor.')


def _revisao(*, ator, trabalhador_id, turno_id, vigencia, classificar_legado=False):
    from apps.planejamento.models import Alocacao, Tarefa
    exigir_coordenador(ator)
    if type(vigencia) is not date or vigencia < data_operacional_hoje():
        raise ValidationError('Informe vigência a partir da data operacional de hoje.')
    trabalhador = Trabalhador.objects.filter(pk=trabalhador_id).first()
    if trabalhador is None:
        raise ValidationError('O trabalhador não está mais disponível. Revise novamente.')
    exigir_coordenador(ator, trabalhador.setor_principal_id)
    exigir_setores(ator, [trabalhador.setor_principal_id])
    if not trabalhador.ativo:
        raise ValidationError('Confira o trabalhador inativo antes de trocar o turno.')
    turno = Turno.objects.filter(pk=turno_id, ativo=True).first()
    if turno is None:
        raise ValidationError('Selecione um turno ativo.')
    ultima = trabalhador.mudancas_turno.order_by('-vigencia', '-pk').first()
    if ultima and vigencia <= ultima.vigencia:
        raise ValidationError('A nova vigência deve ser posterior à última mudança registrada. Não sobrescreva o histórico.')
    anterior = trabalhador.turno_em(vigencia)
    if anterior and anterior.pk == turno.pk:
        raise ValidationError('O trabalhador já estará nesse turno na data informada.')
    alocacoes = list(Alocacao.objects.filter(trabalhador=trabalhador, data__gte=vigencia)
                     .select_related('tarefa', 'turno', 'funcao_desempenhada').order_by('pk'))
    # Examinar todas é necessário para rejeitar a troca inteira; nunca exibir as de outro setor.
    exigir_setores(ator, [a.tarefa.setor_id for a in alocacoes])
    for setor_id in {a.tarefa.setor_id for a in alocacoes}:
        exigir_coordenador(ator, setor_id)
    if alocacoes:
        exigir_operacao(ator, 'planejamento.change_alocacao')
    if any(a.tarefa.status in (Tarefa.Status.CONCLUIDA, Tarefa.Status.CANCELADA) for a in alocacoes):
        raise ValidationError('Há alocações em tarefa encerrada. Confira o planejamento antes da troca.')
    if any(a.turno_id is None for a in alocacoes) and not classificar_legado:
        raise ValidationError('Há alocações futuras sem turno. A classificação exige seleção explícita e revisão da lista.')
    dados = {'classificar_legado': bool(classificar_legado), 'trabalhador': trabalhador.pk, 'turno': turno.pk, 'vigencia': vigencia.isoformat(),
             'situacao_trabalhador': [trabalhador.setor_principal_id, trabalhador.funcao_principal_id, trabalhador.ativo],
             'ultima_mudanca': ultima.pk if ultima else None,
             'alocacoes': [[a.pk, a.trabalhador_id, a.tarefa_id, a.data.isoformat(), a.turno_id,
                           a.funcao_desempenhada_id, a.observacao, a.alterado_em.isoformat(),
                           a.tarefa.status, a.tarefa.setor_id, a.tarefa.inicio_previsto.isoformat(),
                           a.tarefa.fim_previsto.isoformat()] for a in alocacoes]}
    resumo = hashlib.sha256(json.dumps(dados, sort_keys=True).encode()).hexdigest()
    return {'trabalhador': trabalhador, 'turno': turno, 'anterior': anterior,
            'vigencia': vigencia, 'alocacoes': alocacoes, 'resumo': resumo}


def revisar_troca_turno(*, ator, trabalhador_id, turno_id, vigencia, classificar_legado=False):
    revisao = _revisao(ator=ator, trabalhador_id=trabalhador_id, turno_id=turno_id, vigencia=vigencia, classificar_legado=classificar_legado)
    revisao['confirmacao'] = signing.dumps({'ator': ator.pk, 'trabalhador': trabalhador_id,
        'turno': turno_id, 'classificar_legado': bool(classificar_legado), 'vigencia': vigencia.isoformat(), 'resumo': revisao['resumo']}, salt='troca-turno')
    return revisao


@transaction.atomic
def confirmar_troca_turno(*, ator, confirmacao, trabalhador_id=None):
    from apps.planejamento.models import Alocacao, Tarefa, HistoricoTurnoAlocacao
    ator = travar_autorizacao(ator)
    exigir_coordenador(ator)
    try:
        dados = signing.loads(confirmacao, salt='troca-turno', max_age=1800)
        if dados['ator'] != ator.pk:
            raise signing.BadSignature()
        if trabalhador_id is not None and dados['trabalhador'] != trabalhador_id:
            raise signing.BadSignature()
        vigencia = date.fromisoformat(dados['vigencia'])
        if not isinstance(dados['classificar_legado'], bool) or not isinstance(dados['resumo'], str) or dados['turno'] not in ('T1', 'T2', 'T3'):
            raise signing.BadSignature()
    except (signing.BadSignature, KeyError, TypeError, ValueError) as erro:
        raise ValidationError('Revisão inválida ou expirada. Revise a troca novamente.') from erro
    # Mesma ordem de bloqueios de Alocacao.save: tarefas e depois trabalhador.
    tarefa_ids = set(Alocacao.objects.filter(trabalhador_id=dados['trabalhador'], data__gte=vigencia)
                     .values_list('tarefa_id', flat=True))
    list(Tarefa.objects.select_for_update().filter(pk__in=tarefa_ids).order_by('pk'))
    if not Trabalhador.objects.select_for_update().filter(pk=dados['trabalhador']).first():
        raise ValidationError('O trabalhador não está mais disponível. Revise novamente.')
    revisao = _revisao(ator=ator, trabalhador_id=dados['trabalhador'], turno_id=dados['turno'], vigencia=vigencia, classificar_legado=dados['classificar_legado'])
    if revisao['resumo'] != dados['resumo'] or any(a.tarefa_id not in tarefa_ids for a in revisao['alocacoes']):
        raise ValidationError('O planejamento mudou após a revisão. Revise a troca novamente.')
    evento = MudancaTurno(trabalhador=revisao['trabalhador'], vigencia=vigencia,
        turno_anterior=revisao['anterior'], turno_novo=revisao['turno'], registrado_por=ator,
        alocacoes_transferidas=len(revisao['alocacoes']))
    # Inserção interna do evento; edição direta é proibida pelo modelo/Admin.
    evento.full_clean()
    MudancaTurno.objects.bulk_create([evento])
    registros = revisao['alocacoes']
    # Mudar o conjunto junto evita que duas tarefas do mesmo dia conflitem durante a transferência.
    Alocacao.objects.filter(pk__in=[a.pk for a in registros]).update(turno=revisao['turno'])
    for alocacao in registros:
        turno_anterior_id = alocacao.turno_id
        alocacao.turno = revisao['turno']
        alocacao.save(ator=ator)
        if turno_anterior_id != alocacao.turno_id:
            HistoricoTurnoAlocacao.objects.create(alocacao=alocacao, trabalhador_id=alocacao.trabalhador_id,
                tarefa_id=alocacao.tarefa_id, data=alocacao.data, turno_anterior_id=turno_anterior_id,
                turno_novo=alocacao.turno, registrado_por=ator)
    return evento


@transaction.atomic
def criar_trabalhador_com_turno(*, ator, trabalhador, turno=None):
    """Cadastro e primeira vigência juntos, sem transferir planejamento preexistente."""
    if not settings.OP_APP_TURNOS_ENABLED:
        raise PermissionDenied('A operação com turnos não está habilitada.')
    ator = travar_autorizacao(ator)
    if trabalhador.pk is not None or not trabalhador._state.adding:
        raise ValidationError('Para um trabalhador existente, revise a troca de turno.')
    trabalhador.save(ator=ator)
    if turno is not None:
        atual = Turno.objects.filter(pk=getattr(turno, 'pk', turno), ativo=True).first()
        if atual is None:
            raise ValidationError('Selecione um turno ativo.')
        if not trabalhador.ativo:
            raise ValidationError('Confira o trabalhador inativo antes de definir o turno.')
        evento = MudancaTurno(trabalhador=trabalhador, turno_novo=atual,
                             vigencia=data_operacional_hoje(), registrado_por=ator)
        evento.full_clean()
        MudancaTurno.objects.bulk_create([evento])
    return trabalhador
