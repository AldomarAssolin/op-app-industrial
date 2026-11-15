from datetime import date

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
