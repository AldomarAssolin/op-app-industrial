import unicodedata

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
