import unicodedata

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class CadastroNomeado(models.Model):
    """Normalização compartilhada pelos cadastros, inclusive fora do Admin."""

    nome = models.CharField("nome", max_length=150)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        abstract = True
        ordering = ("nome", "pk")

    def clean_fields(self, exclude=None):
        if isinstance(self.nome, str) and (not exclude or "nome" not in exclude):
            self.nome = " ".join(unicodedata.normalize("NFC", self.nome).split())
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        # Model.save() não valida campos automaticamente no Django.
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class Setor(CadastroNomeado):
    descricao = models.TextField("descrição", blank=True)

    class Meta(CadastroNomeado.Meta):
        verbose_name = "setor"
        verbose_name_plural = "setores"
        constraints = [
            models.UniqueConstraint(
                Lower("nome"), name="organizacao_setor_nome_ci_unico",
                violation_error_message="Já existe um setor com este nome.",
            ),
        ]


class Funcao(CadastroNomeado):
    descricao = models.TextField("descrição", blank=True)

    class Meta(CadastroNomeado.Meta):
        verbose_name = "função"
        verbose_name_plural = "funções"
        constraints = [
            models.UniqueConstraint(
                Lower("nome"), name="organizacao_funcao_nome_ci_unico",
                violation_error_message="Já existe uma função com este nome.",
            ),
        ]


class Trabalhador(CadastroNomeado):
    def save(self, *args, ator=None, **kwargs):
        from django.conf import settings
        if not settings.OP_APP_TURNOS_ENABLED or ator is None:
            return super().save(*args, **kwargs)
        from django.db import transaction
        from django.core.exceptions import PermissionDenied
        from .autorizacao import travar_autorizacao, exigir_operacao, administrador, coordenador_no_setor
        with transaction.atomic():
            ator = travar_autorizacao(ator)
            anterior = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
            exigir_operacao(ator, 'organizacao.change_trabalhador' if anterior else 'organizacao.add_trabalhador')
            if not administrador(ator) and not (coordenador_no_setor(ator, self.setor_principal_id)
                    and (anterior is None or coordenador_no_setor(ator, anterior.setor_principal_id))):
                raise PermissionDenied('Alteração do trabalhador exige o Coordenador dos setores envolvidos.')
            return super().save(*args, **kwargs)

    def turno_em(self, dia):
        mudanca = self.mudancas_turno.filter(vigencia__lte=dia).select_related('turno_novo').order_by('-vigencia', '-pk').first()
        return mudanca.turno_novo if mudanca else None

    @property
    def turno_habitual(self):
        from .turnos import data_operacional_hoje
        return self.turno_em(data_operacional_hoje())

    setor_principal = models.ForeignKey(
        Setor, verbose_name="setor principal", on_delete=models.PROTECT,
        related_name="trabalhadores",
    )
    funcao_principal = models.ForeignKey(
        Funcao, verbose_name="função principal", on_delete=models.PROTECT,
        related_name="trabalhadores",
    )

    class Meta(CadastroNomeado.Meta):
        verbose_name = "trabalhador"
        verbose_name_plural = "trabalhadores"

    def __str__(self):
        # Nomes homônimos são permitidos. O ID diferencia as opções no Admin.
        return f"{self.nome} (ID {self.pk})" if self.pk else self.nome


class UsuarioSetor(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="setores_permitidos", verbose_name="usuário")
    setor = models.ForeignKey(Setor, on_delete=models.CASCADE,
                              related_name="acessos_usuarios", verbose_name="setor")

    class Meta:
        verbose_name = "acesso de usuário a setor"
        verbose_name_plural = "acessos de usuários a setores"
        constraints = [models.UniqueConstraint(fields=("usuario", "setor"),
                                               name="organizacao_usuario_setor_unico")]

    def __str__(self):
        return f"{self.usuario} | {self.setor}"


class Turno(models.Model):
    class Codigo(models.TextChoices):
        T1 = 'T1', 'T1'
        T2 = 'T2', 'T2'
        T3 = 'T3', 'T3'

    codigo = models.CharField('turno', max_length=2, primary_key=True, choices=Codigo.choices)
    inicio_referencia = models.TimeField('início de referência', null=True, blank=True)
    fim_referencia = models.TimeField('fim de referência', null=True, blank=True)
    horario_aproximado = models.BooleanField('horário aproximado', default=False)
    ativo = models.BooleanField('ativo', default=True)

    class Meta:
        ordering = ('codigo',)
        constraints = [models.CheckConstraint(condition=models.Q(codigo__in=('T1', 'T2', 'T3')),
                                             name='turno_codigo_valido')]

    def __str__(self):
        return self.codigo

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        obj._codigo_original = obj.pk
        return obj

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if getattr(self, '_codigo_original', self.pk) != self.pk:
            raise ValidationError('A identificação do turno não pode ser alterada.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Inative o turno; não exclua sua referência.')


class MudancaTurno(models.Model):
    trabalhador = models.ForeignKey(Trabalhador, on_delete=models.PROTECT, related_name='mudancas_turno')
    vigencia = models.DateField('data de vigência')
    turno_anterior = models.ForeignKey(Turno, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    turno_novo = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name='+')
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    registrado_em = models.DateTimeField(auto_now_add=True)
    alocacoes_transferidas = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('vigencia', 'pk')
        constraints = [models.UniqueConstraint(fields=('trabalhador', 'vigencia'), name='mudanca_turno_vigencia_unica')]

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Use a revisão e confirmação de troca de turno.')

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('O histórico de turno deve ser preservado.')


class ResponsavelSetor(models.Model):
    setor = models.OneToOneField(Setor, on_delete=models.PROTECT, related_name='responsavel_operacional')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='responsabilidades_setor')

    class Meta:
        verbose_name = 'coordenador responsável pelo setor'
        verbose_name_plural = 'coordenadores responsáveis pelos setores'

    def __str__(self):
        return f'{self.setor} · {self.usuario}'

    def save(self, *args, ator=None, **kwargs):
        from .acessos_turno import salvar_responsavel
        return salvar_responsavel(self, ator=ator, args=args, kwargs=kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Substitua o responsável; preserve o histórico.')


class VinculoLiderTurno(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='vinculos_turno')
    setor = models.ForeignKey(Setor, on_delete=models.PROTECT, related_name='vinculos_lider_turno')
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name='+')
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'acesso de líder a setor e turno'
        verbose_name_plural = 'acessos de líderes a setores e turnos'
        constraints = [models.UniqueConstraint(fields=('usuario', 'setor', 'turno'), name='lider_setor_turno_unico')]

    def __str__(self):
        return f'{self.usuario} · {self.setor} · {self.turno}'

    def save(self, *args, ator=None, **kwargs):
        from .acessos_turno import salvar_vinculo
        return salvar_vinculo(self, ator=ator, args=args, kwargs=kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Inative o vínculo; preserve o histórico.')


class HistoricoAcessoTurno(models.Model):
    setor = models.ForeignKey(Setor, on_delete=models.PROTECT, related_name='+')
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    registrado_em = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=30)
    alteracao = models.JSONField()

    class Meta:
        ordering = ('registrado_em', 'pk')
        verbose_name = 'registro de acesso por turno'
        verbose_name_plural = 'histórico de acessos por turno'

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if not self._state.adding:
            raise ValidationError('O histórico de acesso não pode ser alterado.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('O histórico de acesso deve ser preservado.')
