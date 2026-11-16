from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction


# Escopo de dados é conferido separadamente; os grupos concedem operações.
LEITURA = {
    "organizacao": {"setor": "view", "funcao": "view", "trabalhador": "view"},
    "planejamento": {"tarefa": "view", "historicotarefa": "view", "alocacao": "view"},
}


class Command(BaseCommand):
    help = "Cria/atualiza os quatro grupos do OP-APP após migrate. Não altera usuários nem vínculos."

    @transaction.atomic
    def handle(self, *args, **options):
        import copy
        perfis = {}
        perfis["Consulta"] = copy.deepcopy(LEITURA)
        perfis["Líder"] = copy.deepcopy(LEITURA)
        perfis["Líder"]["organizacao"].pop("setor")
        perfis["Líder"]["planejamento"].update(tarefa="view add change", alocacao="view add change delete")
        perfis["Coordenador"] = copy.deepcopy(perfis["Líder"])
        perfis["Coordenador"]["organizacao"]["setor"] = "view"
        perfis["Coordenador"]["organizacao"]["trabalhador"] = "view add change"
        perfis["Administrador"] = copy.deepcopy(perfis["Coordenador"])
        for modelo in ("setor", "funcao", "trabalhador"):
            perfis["Administrador"]["organizacao"][modelo] = "view add change delete"
        for nome, apps in perfis.items():
            grupo, _ = Group.objects.get_or_create(name=nome)
            permissoes = []
            for app, modelos in apps.items():
                for modelo, operacoes in modelos.items():
                    for operacao in operacoes.split():
                        permissoes.append(Permission.objects.get(
                            content_type__app_label=app, codename=f"{operacao}_{modelo}"))
            grupo.permissions.set(permissoes)
            self.stdout.write(f"{nome}: permissões sincronizadas")
