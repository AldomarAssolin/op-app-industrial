"""Política compartilhada pelo Admin e serviços. Não confunde usuário com trabalhador."""
from django.core.exceptions import PermissionDenied

ADMINISTRADOR = "Administrador"
COORDENADOR = "Coordenador"
LIDER = "Líder"
CONSULTA = "Consulta"


def administrador(ator):
    return bool(ator and ator.is_authenticated and ator.is_active and (
        ator.is_superuser or ator.groups.filter(name=ADMINISTRADOR).exists()))


def exigir_operacao(ator, permissao):
    if (ator is None or not ator.is_authenticated or not ator.is_active
            or not ator.has_perm(permissao)):
        raise PermissionDenied("Operação não autorizada.")
    if not ator.is_superuser and not permissao.split(".")[-1].startswith("view_"):
        grupos = set(ator.groups.values_list("name", flat=True))
        if CONSULTA in grupos and not grupos.intersection({ADMINISTRADOR, COORDENADOR, LIDER}):
            raise PermissionDenied("Perfil Consulta não pode gravar alterações.")


def setores_do_usuario(ator):
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


def filtrar_escopo(ator, queryset):
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


def exigir_escopo_objeto(ator, objeto):
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
