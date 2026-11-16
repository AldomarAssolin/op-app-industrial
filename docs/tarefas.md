# Tarefas operacionais — issue #3

## Modelo

Uma tarefa representa uma atividade de produção, como **Eixo THC 95**, que pode durar um dia, várias semanas ou atravessar meses. Não é uma ordem de produção completa e não mede horas nem produtividade.

Campos: título obrigatório (até 200 caracteres, espaços normalizados), descrição opcional, setor obrigatório, início previsto, conclusão prevista, status e observações opcionais. As datas são obrigatórias e `fim_previsto >= inicio_previsto`; início e fim no mesmo dia são permitidos. Títulos repetidos são permitidos e o ID identifica cada tarefa.

## Estados e transições

Toda tarefa nova começa **PENDENTE**. O usuário autorizado muda o estado no Admin:

| Estado atual | Próximos estados permitidos |
| --- | --- |
| PENDENTE | EM_ANDAMENTO ou CANCELADA |
| EM_ANDAMENTO | CONCLUIDA ou CANCELADA |
| CONCLUIDA | PENDENTE (reabertura) |
| CANCELADA | PENDENTE (reabertura) |

Salvar sem mudar o estado é permitido. Concluir exige passar por EM_ANDAMENTO; para retomar uma tarefa encerrada, primeiro selecione PENDENTE. Depois é possível iniciá-la novamente. Reabertura exige permissão de alteração de tarefa e setor autorizado conforme a política da issue #6, em [seguranca-piloto.md](seguranca-piloto.md).

Prazo vencido **não conclui nem cancela automaticamente** uma tarefa. Por exemplo, se o prazo de Eixo THC 95 terminou e falta material, ela pode continuar em andamento, com essa informação em observações.

## Replanejamento e histórico

- Tarefas pendentes ou em andamento podem mudar período e setor, respeitando a ordem das datas.
- Tarefas concluídas ou canceladas precisam voltar a PENDENTE para mudar período/setor. Reabrir e replanejar podem ocorrer no mesmo salvamento.
- Descrição, título e observações continuam editáveis em estados finais, para correções e notas.
- O registro inicial e cada mudança de estado, período ou setor geram um `HistoricoTarefa` com data/hora e uma fotografia dos quatro valores. Salvar sem mudança operacional não duplica registros.
- A tarefa e seu registro são gravados na mesma transação. Atualizações bloqueiam a linha da tarefa enquanto validam o estado persistido e gravam o histórico.
- Novos registros gerados pelo Admin incluem o usuário autenticado; registros anteriores/seed podem ter autor vazio. O histórico aparece somente para leitura no Admin, restrito aos setores autorizados; não pode ser criado, alterado ou excluído pelo formulário. Ele não substitui o log nativo de autoria das edições no Admin, nem é um registro inviolável para quem tem acesso direto ao banco.

Toda tarefa criada pelo fluxo suportado já possui histórico. A exclusão fica desabilitada no Admin e `PROTECT` no vínculo histórico → tarefa bloqueia exclusão pelo ORM, inclusive em lote. Para desistir de uma atividade, cancele-a. O setor atual e setores preservados no histórico também são protegidos contra exclusão. Setores inativos continuam disponíveis, conforme o comportamento dos cadastros organizacionais.

Normalização, validação de transições e histórico são aplicados em `save()`, inclusive em criação/edição pelo ORM. `update_fields` considera somente os valores efetivamente salvos. As constraints do PostgreSQL reforçam o intervalo de datas e a lista de status válidos. `bulk_create`, `bulk_update`, `QuerySet.update` e SQL direto ignoram o ciclo de `save()` e não são suportados para alterações operacionais: não garantem transições nem histórico. Futuras importações e alocações devem usar o fluxo validado.

## Exemplo e conferência no Admin

1. Aplicar migrações com `python manage.py migrate` e abrir `/admin/` com usuário administrativo.
2. Em **Planejamento operacional → Tarefas**, cadastrar **Eixo THC 95**, setor **Caldeiraria**, início **02/11/2026**, conclusão **20/11/2026** e status **Pendente**. O intervalo cobre três semanas; datas no formulário seguem o formato configurado pelo Django, inclusive ISO `2026-11-02`.
3. Filtrar a listagem por setor e status; buscar `THC 95`.
4. Mudar para **Em andamento**, depois para **Concluída**; conferir o histórico inicial e as duas alterações.
5. Tentar mudar diretamente de **Concluída** para **Em andamento**: o formulário deve rejeitar. Reabrir como **Pendente** para retomar.
6. Replanejar a conclusão para **04/12/2026**, conferindo que o período anterior permanece no histórico.
7. Informar conclusão anterior ao início: o formulário deve rejeitar sem gravar alteração ou histórico.
8. Cancelar a tarefa pendente e confirmar que ela continua consultável, sem opção de exclusão.

As telas usam as permissões nativas do Django. Para apenas consultar tarefas e seu histórico no Admin, conceder `view_tarefa` e `view_historicotarefa`; alteração exige `change_tarefa`. Nenhum endpoint público, integração externa ou permissão de operação de máquinas é adicionado.

## Verificação automatizada

```bash
python manage.py check
python manage.py migrate --noinput
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test -v 2 --noinput
```

Os testes novos cobrem períodos multissemanas, obrigatoriedade, constraints reais do banco, todas as combinações de transições, vencimento sem conclusão automática, reabertura, replanejamento, gravação parcial, rollback, proteção de exclusão e fluxos do Admin. O CI usa Python 3.12 e PostgreSQL 17 pelo Compose existente.

As alocações diárias foram acrescentadas na issue #4: consulte [alocacoes.md](alocacoes.md). O replanejamento agora precisa abranger todos os dias já alocados; corrigir/remover dias incompatíveis deve preceder a redução do período. Encerrar uma tarefa preserva as alocações e impede novas gravações nelas até reabrir. Equipamentos, manutenção, apontamento de produção e produtividade permanecem fora do escopo.
