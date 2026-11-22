from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import Setor


class CriacaoSetorAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('configurar_perfis', verbosity=0)
        cls.root = get_user_model().objects.create_superuser(username='root_setores')
        cls.usuarios = {}
        for grupo in ('Administrador', 'Coordenador', 'Líder', 'Consulta'):
            usuario = get_user_model().objects.create_user(username=grupo, is_staff=True)
            usuario.groups.add(Group.objects.get(name=grupo))
            cls.usuarios[grupo] = usuario

    def test_superuser_e_administrador_criam_setor_com_e_sem_turnos(self):
        url = reverse('admin:organizacao_setor_add')
        for turnos in (True, False):
            for usuario in (self.root, self.usuarios['Administrador']):
                with self.subTest(turnos=turnos, usuario=usuario.username), override_settings(OP_APP_TURNOS_ENABLED=turnos):
                    self.client.force_login(usuario)
                    self.assertEqual(self.client.get(url).status_code, 200)
                    nome = f'Setor {usuario.pk} {turnos}'
                    resposta = self.client.post(url, {'nome':nome, 'descricao':'QA', 'ativo':'on'})
                    self.assertEqual(resposta.status_code,302)
                    self.assertTrue(Setor.objects.filter(nome=nome).exists())

    def test_demais_perfis_nao_criam_setor(self):
        url = reverse('admin:organizacao_setor_add')
        for turnos in (True, False):
            for nome in ('Coordenador', 'Líder', 'Consulta'):
                with self.subTest(turnos=turnos, perfil=nome), override_settings(OP_APP_TURNOS_ENABLED=turnos):
                    self.client.force_login(self.usuarios[nome])
                    self.assertEqual(self.client.get(url).status_code,403)
                    self.assertEqual(self.client.post(url, {'nome':'Setor proibido'}).status_code,403)
        self.assertFalse(Setor.objects.exists())
