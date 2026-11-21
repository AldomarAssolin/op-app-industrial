from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction

from .autorizacao import COORDENADOR, LIDER, ator_atual, coordenador_no_setor, exigir_operacao
from .models import HistoricoAcessoTurno, ResponsavelSetor, Setor, UsuarioSetor, VinculoLiderTurno


def _travar_usuarios(ids):
    return list(get_user_model().objects.select_for_update().filter(pk__in=ids).order_by('pk'))


@transaction.atomic
def salvar_responsavel(obj, *, ator, args, kwargs):
    if kwargs.get('update_fields') is not None:
        raise ValidationError('Salve a configuração completa; atualização parcial de acesso não é permitida.')
    if not settings.OP_APP_TURNOS_ENABLED:
        raise PermissionDenied('Ative a operação com turnos antes de configurar responsabilidades.')
    ator = ator_atual(ator)
    if not ator or not ator.is_superuser:
        raise PermissionDenied('A configuração de responsáveis cabe ao superusuário técnico.')
    anterior = ResponsavelSetor.objects.filter(pk=obj.pk).first() if obj.pk else None
    ids = {ator.pk, obj.usuario_id} | ({anterior.usuario_id} if anterior else set())
    _travar_usuarios(ids)
    ator = ator_atual(ator)
    if not ator or not ator.is_superuser:
        raise PermissionDenied('A configuração de responsáveis cabe ao superusuário técnico.')
    Setor.objects.select_for_update().get(pk=obj.setor_id)
    if anterior:
        atual = ResponsavelSetor.objects.select_for_update().get(pk=obj.pk)
        if (atual.usuario_id, atual.setor_id) != (anterior.usuario_id, anterior.setor_id):
            raise ValidationError('A responsabilidade mudou. Recarregue antes de substituir.')
        if anterior.setor_id != obj.setor_id:
            raise ValidationError('Não mova a responsabilidade entre setores; configure o setor de destino.')
    destino = get_user_model().objects.filter(pk=obj.usuario_id, is_active=True, groups__name=COORDENADOR).exists()
    if not destino:
        raise ValidationError({'usuario': 'Selecione uma conta ativa com perfil Coordenador.'})
    obj.full_clean()
    resultado = models.Model.save(obj, *args, **kwargs)
    if anterior is None or anterior.usuario_id != obj.usuario_id:
        HistoricoAcessoTurno.objects.create(setor_id=obj.setor_id, registrado_por=ator, tipo='responsavel',
            alteracao={'anterior': anterior.usuario_id if anterior else None, 'novo': obj.usuario_id})
    return resultado


@transaction.atomic
def salvar_vinculo(obj, *, ator, args, kwargs):
    if kwargs.get('update_fields') is not None:
        raise ValidationError('Salve a configuração completa; atualização parcial de acesso não é permitida.')
    if not settings.OP_APP_TURNOS_ENABLED:
        raise PermissionDenied('A operação com turnos não está habilitada.')
    ator = ator_atual(ator)
    if ator is None:
        raise PermissionDenied('Operação não autorizada.')
    _travar_usuarios({ator.pk, obj.usuario_id})
    ator = ator_atual(ator)
    exigir_operacao(ator, 'organizacao.change_vinculoliderturno' if obj.pk else 'organizacao.add_vinculoliderturno')
    if not coordenador_no_setor(ator, obj.setor_id) and not ator.is_superuser:
        raise PermissionDenied('Somente o Coordenador responsável pode manter vínculos deste setor.')
    anterior = VinculoLiderTurno.objects.select_for_update().filter(pk=obj.pk).first() if obj.pk else None
    if anterior and (anterior.usuario_id, anterior.setor_id, anterior.turno_id) != (obj.usuario_id, obj.setor_id, obj.turno_id):
        raise ValidationError('Inative o vínculo anterior e crie outro; não altere sua identidade.')
    if obj.ativo or anterior is None:
        if not get_user_model().objects.filter(pk=obj.usuario_id, is_active=True, groups__name=LIDER).exists():
            raise ValidationError({'usuario': 'Selecione uma conta ativa com perfil Líder.'})
        if not UsuarioSetor.objects.filter(usuario_id=obj.usuario_id, setor_id=obj.setor_id).exists():
            raise ValidationError('O acesso básico da conta ao setor deve ser preparado pelo responsável técnico.')
        if not obj.turno.ativo:
            raise ValidationError({'turno': 'Selecione um turno ativo.'})
    obj.full_clean()
    resultado = models.Model.save(obj, *args, **kwargs)
    if anterior is None or anterior.ativo != obj.ativo:
        HistoricoAcessoTurno.objects.create(setor_id=obj.setor_id, registrado_por=ator, tipo='vinculo_lider',
            alteracao={'usuario': obj.usuario_id, 'turno': obj.turno_id,
                       'anterior': anterior.ativo if anterior else None, 'ativo': obj.ativo})
    return resultado
