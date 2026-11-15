from datetime import date

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import models, router, transaction
from django.db.models import F, Q


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

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and not update_fields:
            return
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        kwargs["using"] = using
        with transaction.atomic(using=using):
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
            self.full_clean()
            super().save(*args, **kwargs)
            if anterior is None or any(
                getattr(self, campo) != getattr(anterior, campo) for campo in self.CAMPOS_HISTORICO
            ):
                HistoricoTarefa.objects.using(using).create(
                    tarefa=self, **{campo: getattr(self, campo) for campo in self.CAMPOS_HISTORICO}
                )


class HistoricoTarefa(models.Model):
    """Fotografia do planejamento inicial e de cada alteração operacional."""

    tarefa = models.ForeignKey(Tarefa, on_delete=models.PROTECT, related_name="historico")
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)
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
    if (ator is None or not ator.is_authenticated or not ator.is_active
            or not ator.has_perm(f"planejamento.{operacao}_alocacao")):
        raise PermissionDenied("Usuário sem permissão para esta operação de alocação.")


class Alocacao(models.Model):
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
            anterior = type(self).objects.filter(pk=self.pk).first() if self.pk else None
            if anterior and update_fields is not None:
                for campo in ("trabalhador", "tarefa", "data", "funcao_desempenhada", "observacao"):
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
                                         for campo in ("tarefa_id", "trabalhador_id", "data")):
                raise ValidationError("A alocação mudou durante a operação. Recarregue e tente novamente.")
            if anterior:
                exigir_permissao(ator, "change")
                self.criado_por_id = anterior.criado_por_id
            else:
                exigir_permissao(ator, "add")
                self.criado_por = ator
            self.alterado_por = ator
            self.full_clean()
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"alterado_por", "alterado_em"}
            super().save(*args, **kwargs)

    def delete(self, *args, ator=None, **kwargs):
        exigir_permissao(ator, "delete")
        return super().delete(*args, **kwargs)
