from datetime import date

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import models, router, transaction
from django.db.models import F, Q

from apps.organizacao.autorizacao import (exigir_operacao, exigir_escopo_objeto, travar_autorizacao,
    administrador, coordenador_no_setor, exigir_setor_turno, turnos_permitidos, filtrar_escopo)


class Tarefa(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        CANCELADA = "CANCELADA", "Cancelada"

    titulo = models.CharField("título", max_length=200)
    descricao = models.TextField("descrição", blank=True)
    setor = models.ForeignKey(
        "organizacao.Setor", on_delete=models.PROTECT, related_name="tarefas",
        verbose_name="setor",
    )
    inicio_previsto = models.DateField("início previsto")
    fim_previsto = models.DateField("conclusão prevista")
    status = models.CharField("status", max_length=20, choices=Status.choices,
                              default=Status.PENDENTE)
    observacoes = models.TextField("observações", blank=True)

    # Toda retomada passa por PENDENTE; concluir exige início explícito.
    TRANSICOES = {
        Status.PENDENTE: {Status.EM_ANDAMENTO, Status.CANCELADA},
        Status.EM_ANDAMENTO: {Status.CONCLUIDA, Status.CANCELADA},
        Status.CONCLUIDA: {Status.PENDENTE},
        Status.CANCELADA: {Status.PENDENTE},
    }
    CAMPOS_HISTORICO = ("status", "inicio_previsto", "fim_previsto", "setor_id")

    class Meta:
        verbose_name = "tarefa"
        verbose_name_plural = "tarefas"
        ordering = ("inicio_previsto", "pk")
        constraints = [
            models.CheckConstraint(condition=Q(fim_previsto__gte=F("inicio_previsto")),
                                   name="planejamento_tarefa_periodo_valido"),
            models.CheckConstraint(
                condition=Q(status__in=["PENDENTE", "EM_ANDAMENTO", "CONCLUIDA", "CANCELADA"]),
                name="planejamento_tarefa_status_valido",
            ),
        ]

    def __str__(self):
        return self.titulo

    def clean_fields(self, exclude=None):
        if isinstance(self.titulo, str) and (not exclude or "titulo" not in exclude):
            self.titulo = " ".join(self.titulo.split())
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        erros = {}
        if (isinstance(self.inicio_previsto, date) and isinstance(self.fim_previsto, date)
                and self.fim_previsto < self.inicio_previsto):
            erros["fim_previsto"] = "A conclusão prevista não pode anteceder o início."
        anterior = None
        if self.pk is not None:
            anterior = type(self).objects.using(self._state.db).filter(pk=self.pk).first()
        if anterior is None:
            if self.status != self.Status.PENDENTE:
                erros["status"] = "Uma nova tarefa deve começar como pendente."
        else:
            if (self.status != anterior.status
                    and self.status not in self.TRANSICOES.get(anterior.status, set())):
                erros["status"] = "Transição inválida. Para reabrir, selecione Pendente."
            if (anterior.status in {self.Status.CONCLUIDA, self.Status.CANCELADA}
                    and self.status != self.Status.PENDENTE):
                for campo in ("inicio_previsto", "fim_previsto", "setor_id"):
                    if getattr(self, campo) != getattr(anterior, campo):
                        erros["setor" if campo == "setor_id" else campo] = (
                            "Reabra a tarefa como pendente antes de replanejar."
                        )
        if erros:
            raise ValidationError(erros)

        if self.pk and isinstance(self.inicio_previsto, date) and isinstance(self.fim_previsto, date):
            if self.alocacoes.exclude(data__range=(self.inicio_previsto, self.fim_previsto)).exists():
                raise ValidationError({
                    "fim_previsto": "O período deve abranger todas as alocações existentes. Corrija os dias antes de reduzir o prazo."
                })

    def save(self, *args, ator=None, turno_operacao=None, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and not update_fields:
            return
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        kwargs["using"] = using
        with transaction.atomic(using=using):
            if ator is not None:
                ator = travar_autorizacao(ator)
            anterior = None
            if self.pk is not None:
                anterior = type(self).objects.using(using).select_for_update().filter(pk=self.pk).first()
            if anterior is not None:
                if update_fields is not None:
                    # Valida e registra apenas os valores que serão persistidos.
                    for campo in self._meta.concrete_fields:
                        if (not campo.primary_key and campo.name not in update_fields
                                and campo.attname not in update_fields):
                            setattr(self, campo.attname, getattr(anterior, campo.attname))
            if ator is not None:
                exigir_operacao(ator, "planejamento.change_tarefa" if anterior else "planejamento.add_tarefa")
                exigir_escopo_objeto(ator, self)
                if anterior is not None:
                    exigir_escopo_objeto(ator, anterior)
            if settings.OP_APP_TURNOS_ENABLED and turno_operacao is not None and ator is None:
                raise PermissionDenied('Informe o autor da operação por turno.')
            if settings.OP_APP_TURNOS_ENABLED and ator is not None:
                irrestrito = administrador(ator) or (
                    coordenador_no_setor(ator, self.setor_id)
                    and (anterior is None or coordenador_no_setor(ator, anterior.setor_id)))
                if not irrestrito:
                    if turno_operacao is None:
                        raise PermissionDenied('Informe o turno autorizado desta operação.')
                    codigo = getattr(turno_operacao, 'pk', turno_operacao)
                    exigir_setor_turno(ator, self.setor_id, codigo)
                    if anterior is not None and not (TurnoTarefa.objects.filter(tarefa=self, turno_id=codigo, ativo=True).exists()
                            or self.alocacoes.filter(turno_id=codigo).exists()):
                        raise PermissionDenied('Tarefa não disponível para este turno.')
                    if anterior is None and self.observacoes:
                        raise PermissionDenied('Use a observação do turno; observações gerais cabem ao Coordenador.')
                    if anterior is not None:
                        campos_gerais = ('titulo', 'descricao', 'setor_id', 'inicio_previsto', 'fim_previsto', 'observacoes')
                        if any(getattr(self, campo) != getattr(anterior, campo) for campo in campos_gerais):
                            raise PermissionDenied('Dados gerais da tarefa são responsabilidade do Coordenador.')
                        if self.status != anterior.status:
                            if (anterior.status, self.status) not in {
                                (self.Status.PENDENTE, self.Status.EM_ANDAMENTO),
                                (self.Status.EM_ANDAMENTO, self.Status.CONCLUIDA)}:
                                raise PermissionDenied('Cancelamento e reabertura exigem o Coordenador.')
                            if self.status == self.Status.CONCLUIDA:
                                from apps.organizacao.turnos import data_operacional_hoje
                                if self.alocacoes.filter(data__gte=data_operacional_hoje()).exclude(turno_id=codigo).exists():
                                    raise ValidationError('Há planejamento pendente em outro turno ou sem classificação. Procure o Coordenador para encerrar.')
                if turno_operacao is not None:
                    codigo = getattr(turno_operacao, 'pk', turno_operacao)
                    from apps.organizacao.models import Turno
                    if not Turno.objects.filter(pk=codigo, ativo=True).exists():
                        raise ValidationError('Selecione um turno ativo.')
            self.full_clean()
            super().save(*args, **kwargs)
            if settings.OP_APP_TURNOS_ENABLED and anterior is None and turno_operacao is not None:
                TurnoTarefa.objects.bulk_create([TurnoTarefa(tarefa=self, turno_id=getattr(turno_operacao, 'pk', turno_operacao), registrado_por=ator)])
            if anterior is None or any(
                getattr(self, campo) != getattr(anterior, campo) for campo in self.CAMPOS_HISTORICO
            ):
                HistoricoTarefa.objects.using(using).create(
                    tarefa=self, registrado_por=ator, turno_operacao_id=getattr(turno_operacao, 'pk', turno_operacao) if settings.OP_APP_TURNOS_ENABLED else None, **{campo: getattr(self, campo) for campo in self.CAMPOS_HISTORICO}
                )


class HistoricoTarefa(models.Model):
    turno_operacao = models.ForeignKey('organizacao.Turno', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    """Fotografia do planejamento inicial e de cada alteração operacional."""

    tarefa = models.ForeignKey(Tarefa, on_delete=models.PROTECT, related_name="historico")
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        editable=False, on_delete=models.PROTECT, related_name="historico_tarefas", verbose_name="registrado por")
    status = models.CharField(max_length=20, choices=Tarefa.Status.choices)
    inicio_previsto = models.DateField("início previsto")
    fim_previsto = models.DateField("conclusão prevista")
    setor = models.ForeignKey("organizacao.Setor", on_delete=models.PROTECT,
                              related_name="historico_tarefas")

    class Meta:
        verbose_name = "registro de planejamento"
        verbose_name_plural = "histórico do planejamento"
        ordering = ("registrado_em", "pk")


def exigir_permissao(ator, operacao):
    exigir_operacao(ator, f"planejamento.{operacao}_alocacao")


class Alocacao(models.Model):
    turno = models.ForeignKey('organizacao.Turno', verbose_name='turno', null=True, blank=True,
                              on_delete=models.PROTECT, related_name='alocacoes')
    trabalhador = models.ForeignKey("organizacao.Trabalhador", on_delete=models.PROTECT,
                                    related_name="alocacoes", verbose_name="trabalhador")
    tarefa = models.ForeignKey(Tarefa, on_delete=models.PROTECT, related_name="alocacoes")
    data = models.DateField("data")
    funcao_desempenhada = models.ForeignKey("organizacao.Funcao", on_delete=models.PROTECT,
                                           related_name="alocacoes", verbose_name="função desempenhada")
    observacao = models.TextField("observação", blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="alocacoes_criadas", editable=False)
    alterado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                     related_name="alocacoes_alteradas", editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    alterado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "alocação diária"
        verbose_name_plural = "alocações diárias"
        ordering = ("data", "trabalhador_id", "pk")
        constraints = [models.UniqueConstraint(
            fields=("trabalhador", "tarefa", "data"), name="planejamento_alocacao_dia_unico",
            violation_error_message="Este trabalhador já está alocado nesta tarefa nesta data.",
        )]
        indexes = [models.Index(fields=("data", "tarefa"), name="alocacao_data_tarefa_idx")]

    def __str__(self):
        return f"{self.trabalhador} | {self.tarefa} | {self.data}"

    def clean(self):
        super().clean()
        erros = {}
        # Campos inválidos também passam por clean() no ModelForm.
        if self.trabalhador_id:
            from apps.organizacao.models import Trabalhador
            trabalhador = Trabalhador.objects.filter(pk=self.trabalhador_id).first()
            if trabalhador is not None and not trabalhador.ativo:
                erros["trabalhador"] = "Trabalhador inativo não pode receber alocações."
        if self.tarefa_id:
            tarefa = Tarefa.objects.filter(pk=self.tarefa_id).first()
            if tarefa is not None:
                if tarefa.status in {Tarefa.Status.CONCLUIDA, Tarefa.Status.CANCELADA}:
                    erros["tarefa"] = "Reabra a tarefa antes de criar ou alterar alocações."
                if isinstance(self.data, date) and not tarefa.inicio_previsto <= self.data <= tarefa.fim_previsto:
                    erros["data"] = "A data deve estar dentro do período previsto da tarefa."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, ator=None, **kwargs):
        from apps.organizacao.models import Trabalhador
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and not update_fields:
            return
        # A aplicação usa um único banco PostgreSQL.
        exigir_permissao(ator, "add" if self._state.adding else "change")
        with transaction.atomic():
            ator = travar_autorizacao(ator)
            exigir_permissao(ator, 'add' if self._state.adding else 'change')
            anterior = type(self).objects.filter(pk=self.pk).first() if self.pk else None
            if anterior and update_fields is not None:
                for campo in ("trabalhador", "tarefa", "data", "funcao_desempenhada", "observacao", "turno"):
                    field = self._meta.get_field(campo)
                    if campo not in update_fields and field.attname not in update_fields:
                        setattr(self, field.attname, getattr(anterior, field.attname))
            # Mesma linha bloqueada pelo replanejamento de Tarefa.save().
            tarefas = {self.tarefa_id} | ({anterior.tarefa_id} if anterior else set())
            trabalhadores = {self.trabalhador_id} | ({anterior.trabalhador_id} if anterior else set())
            list(Tarefa.objects.select_for_update().filter(pk__in=tarefas).order_by("pk"))
            list(Trabalhador.objects.select_for_update().filter(pk__in=trabalhadores).order_by("pk"))
            atual = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
            if anterior and atual is None:
                raise ValidationError("A alocação foi removida. Recarregue a página.")
            if anterior and atual and any(getattr(anterior, campo) != getattr(atual, campo)
                                         for campo in ("tarefa_id", "trabalhador_id", "data", "turno_id")):
                raise ValidationError("A alocação mudou durante a operação. Recarregue e tente novamente.")
            if anterior:
                exigir_permissao(ator, "change")
                self.criado_por_id = anterior.criado_por_id
            else:
                exigir_permissao(ator, "add")
                self.criado_por = ator
            exigir_escopo_objeto(ator, self)
            if anterior:
                exigir_escopo_objeto(ator, anterior)
            self.alterado_por = ator
            if not settings.OP_APP_TURNOS_ENABLED:
                if self.turno_id or (anterior and anterior.turno_id):
                    raise ValidationError('A operação com turnos ainda não está habilitada.')
            else:
                trabalhador_atual = Trabalhador.objects.get(pk=self.trabalhador_id)
                if not self.turno_id:
                    raise ValidationError({'turno': 'Informe o turno antes de confirmar a alocação.'})
                from apps.organizacao.models import Turno
                if not Turno.objects.filter(pk=self.turno_id, ativo=True).exists():
                    raise ValidationError({'turno': 'Selecione um turno ativo.'})
                habitual = trabalhador_atual.turno_em(self.data)
                if habitual is None or habitual.pk != self.turno_id:
                    raise ValidationError({'turno': 'Turno diferente do habitual vigente nessa data. Procure o Coordenador.'})
                if type(self).objects.filter(trabalhador_id=self.trabalhador_id, data=self.data).exclude(pk=self.pk).exclude(turno_id=self.turno_id).exists():
                    raise ValidationError('Há planejamento em outro turno ou sem classificação para essa pessoa e data. Procure o Coordenador.')
            self.full_clean()
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"alterado_por", "alterado_em"}
            super().save(*args, **kwargs)
            if settings.OP_APP_TURNOS_ENABLED and (anterior is None or anterior.turno_id != self.turno_id):
                HistoricoTurnoAlocacao.objects.create(alocacao=self, trabalhador_id=self.trabalhador_id,
                    tarefa_id=self.tarefa_id, data=self.data, turno_anterior_id=anterior.turno_id if anterior else None,
                    turno_novo_id=self.turno_id, registrado_por=ator)

    def delete(self, *args, ator=None, **kwargs):
        exigir_permissao(ator, "delete")
        with transaction.atomic():
            ator = travar_autorizacao(ator)
            exigir_permissao(ator, 'delete')
            snapshot = type(self).objects.get(pk=self.pk)
            list(Tarefa.objects.select_for_update().filter(pk=snapshot.tarefa_id))
            from apps.organizacao.models import Trabalhador
            list(Trabalhador.objects.select_for_update().filter(pk=snapshot.trabalhador_id))
            atual = type(self).objects.select_for_update().get(pk=self.pk)
            if (atual.tarefa_id, atual.trabalhador_id) != (snapshot.tarefa_id, snapshot.trabalhador_id):
                raise ValidationError('A alocação mudou. Recarregue antes de remover.')
            exigir_escopo_objeto(ator, atual)
            return super().delete(*args, **kwargs)


class HistoricoTurnoAlocacao(models.Model):
    alocacao = models.ForeignKey(Alocacao, null=True, on_delete=models.SET_NULL, related_name='historico_turno')
    trabalhador = models.ForeignKey('organizacao.Trabalhador', on_delete=models.PROTECT, related_name='+')
    tarefa = models.ForeignKey(Tarefa, on_delete=models.PROTECT, related_name='+')
    data = models.DateField('data operacional')
    turno_anterior = models.ForeignKey('organizacao.Turno', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    turno_novo = models.ForeignKey('organizacao.Turno', on_delete=models.PROTECT, related_name='+')
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    registrado_em = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('O histórico de turno não pode ser reescrito.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('O histórico de turno deve ser preservado.')

    class Meta:
        ordering = ('registrado_em', 'pk')


class TurnoTarefa(models.Model):
    tarefa = models.ForeignKey(Tarefa, on_delete=models.PROTECT, related_name='participacoes_turno')
    turno = models.ForeignKey('organizacao.Turno', on_delete=models.PROTECT, related_name='+')
    ativo = models.BooleanField(default=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('tarefa', 'turno'), name='tarefa_turno_unico')]

    def save(self, *args, ator=None, **kwargs):
        if not settings.OP_APP_TURNOS_ENABLED:
            raise PermissionDenied('A operação com turnos não está habilitada.')
        with transaction.atomic():
            ator = travar_autorizacao(ator)
            tarefa = Tarefa.objects.select_for_update().get(pk=self.tarefa_id)
            exigir_operacao(ator, 'planejamento.change_tarefa')
            if not administrador(ator) and not coordenador_no_setor(ator, tarefa.setor_id):
                raise PermissionDenied('Somente o Coordenador pode alterar a participação dos turnos.')
            anterior = type(self).objects.filter(pk=self.pk).first() if self.pk else None
            if anterior and (anterior.tarefa_id, anterior.turno_id) != (self.tarefa_id, self.turno_id):
                raise ValidationError('Inative a participação anterior; não altere sua identidade.')
            self.registrado_por_id = anterior.registrado_por_id if anterior else ator.pk
            if self.ativo and not self.turno.ativo:
                raise ValidationError('Selecione um turno ativo.')
            self.full_clean()
            resultado = super().save(*args, **kwargs)
            if anterior is None or anterior.ativo != self.ativo:
                from apps.organizacao.models import HistoricoAcessoTurno
                HistoricoAcessoTurno.objects.create(setor_id=tarefa.setor_id, registrado_por=ator,
                    tipo='participacao_tarefa', alteracao={'tarefa': tarefa.pk, 'turno': self.turno_id,
                    'anterior': anterior.ativo if anterior else None, 'ativo': self.ativo})
            return resultado

    def delete(self, *args, **kwargs):
        raise ValidationError('Inative a participação; preserve os registros.')


class ObservacaoTarefaTurno(models.Model):
    tarefa = models.ForeignKey(Tarefa, on_delete=models.PROTECT, related_name='observacoes_por_turno')
    turno = models.ForeignKey('organizacao.Turno', on_delete=models.PROTECT, related_name='+')
    texto = models.TextField('observação do turno')
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('registrado_em', 'pk')

    def save(self, *args, ator=None, **kwargs):
        if not settings.OP_APP_TURNOS_ENABLED or not self._state.adding:
            raise PermissionDenied('As observações são registros por turno, sem edição do histórico.')
        with transaction.atomic():
            ator = travar_autorizacao(ator)
            tarefa = Tarefa.objects.select_for_update().get(pk=self.tarefa_id)
            exigir_operacao(ator, 'planejamento.change_tarefa')
            exigir_escopo_objeto(ator, tarefa)
            exigir_setor_turno(ator, tarefa.setor_id, self.turno_id)
            if not administrador(ator) and not coordenador_no_setor(ator, tarefa.setor_id):
                if not (TurnoTarefa.objects.filter(tarefa=tarefa, turno_id=self.turno_id, ativo=True).exists()
                        or tarefa.alocacoes.filter(turno_id=self.turno_id).exists()):
                    raise PermissionDenied('Tarefa não disponível para este turno.')
            if not self.texto.strip():
                raise ValidationError('Escreva a observação do turno.')
            self.registrado_por = ator
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied('As observações do turno devem ser preservadas.')
