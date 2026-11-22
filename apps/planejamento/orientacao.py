"""Próximos passos de leitura; sem criar dados ou alterar a política de acesso."""
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from apps.organizacao.autorizacao import (
    administrador, exigir_operacao, filtrar_escopo, setores_do_usuario, pode_manter_equipe,
)
from apps.organizacao.models import Funcao, Trabalhador
from .models import Alocacao, Tarefa


def permite(usuario, permissao):
    try:
        exigir_operacao(usuario, permissao)
    except PermissionDenied:
        return False
    return True


def proximo_passo(usuario, *, setor_id=None, semana=None):
    setores = setores_do_usuario(usuario)
    if setor_id is not None:
        # Nunca converter parâmetro fora do escopo em informação sobre outro setor.
        setores = setores.filter(pk=setor_id)
    tem_setor = setores.exists()

    def resultado(estado, titulo, mensagem, permissao=None, destino=None, acao=None,
                  responsavel=None, configuracao=False):
        pode = (usuario.is_staff and tem_setor and permissao and permite(usuario, permissao))
        if settings.OP_APP_TURNOS_ENABLED and permissao in {'organizacao.add_trabalhador', 'organizacao.change_trabalhador'}:
            pode = pode and pode_manter_equipe(usuario)
        if configuracao:
            pode = usuario.is_staff and administrador(usuario) and permite(usuario, permissao)
        if destino == 'planejamento:planejar':
            pode = tem_setor and permite(usuario, 'planejamento.add_alocacao')
        if destino == 'planejamento:quadro_semanal':
            pode = tem_setor and permite(usuario, 'planejamento.view_alocacao')
        return {'estado': estado, 'titulo': titulo, 'mensagem': mensagem,
                'url': reverse(destino) if pode and destino else None,
                'acao': acao if pode else None,
                'ajuda': f'Peça ao {responsavel} para conferir esse passo.' if responsavel and not pode else None}

    if not tem_setor:
        if administrador(usuario) and setor_id is None:
            return resultado('configuracao', 'Comece pelo setor',
                'Cadastre o setor da operação para organizar a equipe e as tarefas.',
                'organizacao.add_setor', 'admin:organizacao_setor_add', 'Cadastrar setor no Admin',
                'Administrador', configuracao=True)
        if settings.OP_APP_TURNOS_ENABLED:
            return resultado('acesso', 'Confira seu setor e turno autorizados',
                'Peça ao Coordenador para conferir os vínculos de setor e turno. Se sua conta for de Coordenador, procure o responsável pela configuração do OP-APP para conferir a responsabilidade do setor.')
        return resultado('acesso', 'Confira seu acesso aos setores',
            'Sua conta não tem setor autorizado nesta consulta. Procure o responsável pelo OP-APP para conferir seus vínculos.')

    leituras = ('organizacao.view_funcao', 'organizacao.view_trabalhador',
                'planejamento.view_tarefa', 'planejamento.view_alocacao')
    if not all(permite(usuario, p) for p in leituras):
        return resultado('acesso', 'Confira as permissões da sua conta',
            'Não é possível avaliar todos os próximos passos com seu acesso atual. Peça ao responsável pelo OP-APP para conferir suas permissões.')

    if not Funcao.objects.exists():
        return resultado('configuracao', 'Prepare as funções',
            'Cadastre as funções que serão usadas pela equipe e no planejamento.',
            'organizacao.add_funcao', 'admin:organizacao_funcao_add', 'Cadastrar função no Admin',
            'Administrador', configuracao=True)
    trabalhadores = filtrar_escopo(usuario, Trabalhador.objects.all()).filter(setor_principal__in=setores)
    if not trabalhadores.filter(ativo=True).exists():
        return resultado('equipe', 'Prepare a equipe',
            'Não há trabalhadores ativos nos setores desta consulta. Cadastre a equipe ou confira os trabalhadores inativos antes de planejar.',
            'organizacao.add_trabalhador', 'admin:organizacao_trabalhador_add', 'Cadastrar trabalhador no Admin',
            'Coordenador ou Administrador')
    if settings.OP_APP_TURNOS_ENABLED and trabalhadores.filter(ativo=True, _turno_vigente__isnull=True).exists():
        return resultado('turno_habitual', 'Confira o turno habitual da equipe',
            'Há trabalhadores sem turno habitual vigente hoje. Confira a classificação e as mudanças agendadas antes de planejar.',
            'organizacao.change_trabalhador', 'admin:organizacao_trabalhador_changelist', 'Conferir equipe no Admin',
            'Coordenador do setor')
    tarefas = filtrar_escopo(usuario, Tarefa.objects.all()).filter(setor__in=setores)
    if not tarefas.filter(status__in=(Tarefa.Status.PENDENTE, Tarefa.Status.EM_ANDAMENTO)).exists():
        return resultado('tarefas', 'Prepare uma tarefa para planejar',
            'Não há tarefas pendentes ou em andamento nos setores desta consulta. Cadastre uma tarefa com o período previsto ou confira as tarefas encerradas.',
            'planejamento.add_tarefa', 'admin:planejamento_tarefa_add', 'Cadastrar tarefa no Admin',
            'Líder ou Coordenador')
    alocacoes = filtrar_escopo(usuario, Alocacao.objects.all()).filter(tarefa__setor__in=setores)
    if not alocacoes.exists():
        return resultado('alocacoes', 'Faça o primeiro planejamento',
            'Escolha a tarefa, o trabalhador, a função desempenhada e os dias dentro do período previsto. Depois confira o quadro semanal.',
            'planejamento.add_alocacao', 'planejamento:planejar', 'Planejar trabalhadores e dias',
            'Líder ou Coordenador')
    if settings.OP_APP_TURNOS_ENABLED:
        from apps.organizacao.turnos import data_operacional_hoje
        dia = semana or data_operacional_hoje()
    else:
        dia = semana or timezone.localdate()
    inicio = dia - timedelta(days=dia.weekday())
    fim = inicio + timedelta(days=min(6, (date.max - inicio).days))
    if not alocacoes.filter(data__range=(inicio, fim)).exists():
        return resultado('semana_vazia', 'Ainda não há alocações nesta semana',
            'Há planejamento em outros períodos dos setores desta consulta. Consulte outra semana ou planeje os dias desejados.',
            'planejamento.add_alocacao', 'planejamento:planejar', 'Planejar trabalhadores e dias',
            'Líder ou Coordenador')
    return resultado('pronto', 'Continue pela semana planejada',
        'O planejamento já tem alocações nesta semana. Consulte o quadro e use a navegação para continuar o trabalho.',
        destino='planejamento:quadro_semanal', acao='Ver quadro semanal')
