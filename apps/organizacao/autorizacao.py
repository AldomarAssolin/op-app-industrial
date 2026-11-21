"""Política compartilhada pelo Admin e serviços. Não confunde usuário com trabalhador."""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef, Q, Subquery

ADMINISTRADOR = "Administrador"
COORDENADOR = "Coordenador"
LIDER = "Líder"
CONSULTA = "Consulta"


def administrador(ator):
    if settings.OP_APP_TURNOS_ENABLED:
        ator = ator_atual(ator)
    return bool(ator and ator.is_authenticated and ator.is_active and (
        ator.is_superuser or ator.groups.filter(name=ADMINISTRADOR).exists()))


def exigir_operacao(ator, permissao):
    if settings.OP_APP_TURNOS_ENABLED:
        ator = ator_atual(ator)
    if (ator is None or not ator.is_authenticated or not ator.is_active
            or not ator.has_perm(permissao)):
        raise PermissionDenied("Operação não autorizada.")
    if not ator.is_superuser and not permissao.split(".")[-1].startswith("view_"):
        grupos = set(ator.groups.values_list("name", flat=True))
        if CONSULTA in grupos and not grupos.intersection({ADMINISTRADOR, COORDENADOR, LIDER}):
            raise PermissionDenied("Perfil Consulta não pode gravar alterações.")
        if (settings.OP_APP_TURNOS_ENABLED and LIDER in grupos
                and not grupos.intersection({ADMINISTRADOR, COORDENADOR})
                and permissao in {'organizacao.add_trabalhador', 'organizacao.change_trabalhador', 'organizacao.delete_trabalhador'}):
            raise PermissionDenied('Líder não pode alterar o cadastro de trabalhadores.')


def _setores_anteriores(ator):
    from .models import Setor
    if not ator or not ator.is_authenticated or not ator.is_active:
        return Setor.objects.none()
    if administrador(ator):
        return Setor.objects.all()
    return Setor.objects.filter(acessos_usuarios__usuario=ator)


def exigir_setores(ator, ids):
    if administrador(ator):
        return
    ids = {identificador for identificador in ids if identificador is not None}
    permitidos = set(setores_do_usuario(ator).filter(pk__in=ids).values_list("pk", flat=True))
    if not ids.issubset(permitidos):
        raise PermissionDenied("Setor fora do escopo autorizado.")


def _filtrar_escopo_anterior(ator, queryset):
    setores = setores_do_usuario(ator)
    rotulo = queryset.model._meta.label_lower
    if rotulo == "organizacao.setor":
        return queryset.filter(pk__in=setores)
    if rotulo == "organizacao.trabalhador":
        return queryset.filter(setor_principal__in=setores)
    if rotulo == "planejamento.tarefa":
        return queryset.filter(setor__in=setores)
    if rotulo == "planejamento.alocacao":
        return queryset.filter(tarefa__setor__in=setores, trabalhador__setor_principal__in=setores)
    if rotulo == "planejamento.historicotarefa":
        return queryset.filter(tarefa__setor__in=setores, setor__in=setores)
    if rotulo == "organizacao.usuariosetor" and not ator.is_superuser:
        return queryset.none()
    return queryset


def _exigir_escopo_anterior(ator, objeto):
    rotulo = objeto._meta.label_lower
    if rotulo == "organizacao.setor":
        exigir_setores(ator, [objeto.pk])
    elif rotulo == "organizacao.trabalhador":
        exigir_setores(ator, [objeto.setor_principal_id])
    elif rotulo == "planejamento.tarefa":
        exigir_setores(ator, [objeto.setor_id])
    elif rotulo == "planejamento.alocacao":
        from .models import Trabalhador
        from apps.planejamento.models import Tarefa
        ids = list(Tarefa.objects.filter(pk=objeto.tarefa_id).values_list("setor_id", flat=True))
        ids += list(Trabalhador.objects.filter(pk=objeto.trabalhador_id)
                    .values_list("setor_principal_id", flat=True))
        exigir_setores(ator, ids)


def ator_atual(ator):
    from django.contrib.auth import get_user_model
    if not ator or not ator.is_authenticated:
        return None
    return get_user_model().objects.filter(pk=ator.pk, is_active=True).first()


def travar_autorizacao(ator):
    from django.contrib.auth import get_user_model
    if not settings.OP_APP_TURNOS_ENABLED:
        return ator
    atual = ator_atual(ator)
    if atual is None:
        raise PermissionDenied('Operação não autorizada.')
    return get_user_model().objects.select_for_update().get(pk=atual.pk)


def _grupos(ator):
    return set(ator.groups.values_list('name', flat=True)) if ator else set()


def coordenador_no_setor(ator, setor_id):
    from .models import ResponsavelSetor
    ator = ator_atual(ator)
    return bool(ator and COORDENADOR in _grupos(ator)
                and ResponsavelSetor.objects.filter(usuario=ator, setor_id=setor_id).exists())


def _consulta_exclusiva(ator):
    grupos = _grupos(ator)
    return CONSULTA in grupos and not grupos.intersection({LIDER, COORDENADOR, ADMINISTRADOR})


def setores_do_usuario(ator):
    from .models import Setor, UsuarioSetor
    if not settings.OP_APP_TURNOS_ENABLED:
        return _setores_anteriores(ator)
    ator = ator_atual(ator)
    if ator is None:
        return Setor.objects.none()
    if administrador(ator):
        return Setor.objects.all()
    if _consulta_exclusiva(ator):
        return Setor.objects.filter(acessos_usuarios__usuario=ator)
    grupos = _grupos(ator)
    condicao = Q(pk__in=[])
    if COORDENADOR in grupos:
        condicao |= Q(responsavel_operacional__usuario=ator)
    if LIDER in grupos:
        condicao |= Q(vinculos_lider_turno__usuario=ator, vinculos_lider_turno__ativo=True,
                      pk__in=UsuarioSetor.objects.filter(usuario=ator).values('setor_id'))
    return Setor.objects.filter(condicao).distinct()


def turnos_permitidos(ator, setor_id):
    from .models import VinculoLiderTurno
    ator = ator_atual(ator)
    if ator is None or not setores_do_usuario(ator).filter(pk=setor_id).exists():
        return set()
    if administrador(ator) or coordenador_no_setor(ator, setor_id) or _consulta_exclusiva(ator):
        return {'T1', 'T2', 'T3'}
    if LIDER not in _grupos(ator):
        return set()
    return set(VinculoLiderTurno.objects.filter(usuario=ator, setor_id=setor_id, ativo=True).values_list('turno_id', flat=True))


def exigir_setor_turno(ator, setor_id, turno_id):
    if turno_id is None or turno_id not in turnos_permitidos(ator, setor_id):
        raise PermissionDenied('Setor ou turno fora do acesso autorizado.')


def _escopo_turno(ator, queryset, setor_expr, turno_expr):
    from .models import ResponsavelSetor, VinculoLiderTurno, UsuarioSetor
    if administrador(ator):
        return queryset
    if _consulta_exclusiva(ator):
        return queryset.filter(**{setor_expr + '__in': setores_do_usuario(ator)})
    grupos = _grupos(ator)
    coord = ResponsavelSetor.objects.filter(usuario=ator, setor_id=OuterRef(setor_expr))
    lider = VinculoLiderTurno.objects.filter(usuario=ator, setor_id=OuterRef(setor_expr),
        turno_id=OuterRef(turno_expr), ativo=True,
        setor_id__in=UsuarioSetor.objects.filter(usuario=ator).values('setor_id'))
    if COORDENADOR not in grupos:
        coord = coord.none()
    if LIDER not in grupos:
        lider = lider.none()
    chave = setor_expr.replace('__', '_')
    return queryset.annotate(**{f'_coord_{chave}': Exists(coord), f'_lider_{chave}': Exists(lider)}).filter(
        Q(**{f'_coord_{chave}': True}) | Q(**{f'_lider_{chave}': True}))


def filtrar_escopo(ator, queryset, *, data_referencia=None):
    if not settings.OP_APP_TURNOS_ENABLED:
        return _filtrar_escopo_anterior(ator, queryset)
    from .models import MudancaTurno
    from .turnos import data_operacional_hoje
    ator = ator_atual(ator)
    if ator is None:
        return queryset.none()
    rotulo = queryset.model._meta.label_lower
    setores = setores_do_usuario(ator)
    if rotulo == 'organizacao.setor':
        return queryset.filter(pk__in=setores)
    if rotulo == 'organizacao.trabalhador':
        habitual = MudancaTurno.objects.filter(trabalhador_id=OuterRef('pk'), vigencia__lte=data_referencia or data_operacional_hoje()).order_by('-vigencia', '-pk')
        queryset = queryset.annotate(_turno_vigente=Subquery(habitual.values('turno_novo_id')[:1]))
        return _escopo_turno(ator, queryset, 'setor_principal_id', '_turno_vigente')
    if rotulo == 'planejamento.alocacao':
        queryset = _escopo_turno(ator, queryset, 'tarefa__setor_id', 'turno_id')
        return _escopo_turno(ator, queryset, 'trabalhador__setor_principal_id', 'turno_id')
    if rotulo == 'planejamento.tarefa':
        from apps.planejamento.models import Alocacao, TurnoTarefa
        if administrador(ator) or _consulta_exclusiva(ator):
            return queryset.filter(setor__in=setores)
        participacoes = _escopo_turno(ator, TurnoTarefa.objects.filter(ativo=True), 'tarefa__setor_id', 'turno_id')
        alocacoes = filtrar_escopo(ator, Alocacao.objects.all())
        from .models import ResponsavelSetor
        coords = ResponsavelSetor.objects.filter(usuario=ator).values('setor_id') if COORDENADOR in _grupos(ator) else []
        return queryset.filter(setor__in=setores).annotate(
            _participacao_visivel=Exists(participacoes.filter(tarefa_id=OuterRef('pk'))),
            _alocacao_visivel=Exists(alocacoes.filter(tarefa_id=OuterRef('pk')))).filter(
                Q(setor_id__in=coords) | Q(_participacao_visivel=True) | Q(_alocacao_visivel=True))
    if rotulo in {'planejamento.historicotarefa', 'planejamento.observacaotarefaturno', 'planejamento.turnotarefa'}:
        from apps.planejamento.models import Tarefa
        queryset = queryset.filter(tarefa_id__in=filtrar_escopo(ator, Tarefa.objects.all()).values('pk'))
        coluna = 'turno_operacao_id' if rotulo == 'planejamento.historicotarefa' else 'turno_id'
        return _escopo_turno(ator, queryset, 'setor_id' if rotulo == 'planejamento.historicotarefa' else 'tarefa__setor_id', coluna)
    if rotulo == 'planejamento.historicoturnoalocacao':
        queryset = _escopo_turno(ator, queryset, 'tarefa__setor_id', 'turno_novo_id')
        return _escopo_turno(ator, queryset, 'trabalhador__setor_principal_id', 'turno_novo_id')
    if rotulo in {'organizacao.vinculoliderturno', 'organizacao.historicoacessoturno'}:
        if ator.is_superuser:
            return queryset
        return queryset.filter(setor__responsavel_operacional__usuario=ator) if COORDENADOR in _grupos(ator) else queryset.none()
    if rotulo in {'organizacao.usuariosetor', 'organizacao.responsavelsetor'}:
        return queryset if ator.is_superuser else queryset.none()
    if rotulo == 'organizacao.mudancaturno':
        return queryset if administrador(ator) else queryset.filter(trabalhador__setor_principal__responsavel_operacional__usuario=ator) if COORDENADOR in _grupos(ator) else queryset.none()
    return queryset


def exigir_escopo_objeto(ator, objeto):
    if not settings.OP_APP_TURNOS_ENABLED:
        return _exigir_escopo_anterior(ator, objeto)
    rotulo = objeto._meta.label_lower
    if rotulo == 'planejamento.alocacao':
        from .models import Trabalhador
        from apps.planejamento.models import Tarefa
        tarefa = Tarefa.objects.get(pk=objeto.tarefa_id)
        trabalhador = Trabalhador.objects.get(pk=objeto.trabalhador_id)
        if administrador(ator):
            return
        # Legado sem turno só está disponível ao Coordenador/Consulta autorizado, não ao Líder.
        if objeto.turno_id is None:
            if coordenador_no_setor(ator, tarefa.setor_id) and coordenador_no_setor(ator, trabalhador.setor_principal_id):
                return
            if objeto.pk and filtrar_escopo(ator, type(objeto).objects.filter(pk=objeto.pk)).exists():
                return
            raise PermissionDenied('A classificação do turno exige o Coordenador.')
        exigir_setor_turno(ator, tarefa.setor_id, objeto.turno_id)
        if not coordenador_no_setor(ator, tarefa.setor_id) and not _consulta_exclusiva(ator):
            from apps.planejamento.models import TurnoTarefa, Alocacao
            participante = TurnoTarefa.objects.filter(tarefa=tarefa, turno_id=objeto.turno_id, ativo=True).exists()
            existente = Alocacao.objects.filter(tarefa=tarefa, turno_id=objeto.turno_id).exists()
            if not participante and not existente:
                raise PermissionDenied('Tarefa não disponível para este turno.')
        exigir_setor_turno(ator, trabalhador.setor_principal_id, objeto.turno_id)
    elif rotulo == 'planejamento.tarefa' and not objeto.pk:
        exigir_setores(ator, [objeto.setor_id])
    elif rotulo == 'organizacao.trabalhador' and not objeto.pk:
        if not administrador(ator) and not coordenador_no_setor(ator, objeto.setor_principal_id):
            raise PermissionDenied('Cadastro de trabalhador exige o Coordenador responsável.')
    elif rotulo in {'organizacao.setor', 'organizacao.trabalhador', 'planejamento.tarefa', 'planejamento.historicotarefa', 'planejamento.observacaotarefaturno', 'planejamento.turnotarefa'}:
        if rotulo == 'planejamento.tarefa':
            exigir_setores(ator, [objeto.setor_id])
        if rotulo == 'organizacao.trabalhador':
            exigir_setores(ator, [objeto.setor_principal_id])
        if not objeto.pk or not filtrar_escopo(ator, type(objeto).objects.filter(pk=objeto.pk)).exists():
            raise PermissionDenied('Registro fora do acesso autorizado.')


def pode_manter_equipe(ator):
    from .models import ResponsavelSetor
    ator = ator_atual(ator)
    return bool(ator and (administrador(ator) or (COORDENADOR in _grupos(ator)
                and ResponsavelSetor.objects.filter(usuario=ator).exists())))
