# Alocações diárias — issue #4

## O que representa uma alocação

Uma alocação relaciona **trabalhador + tarefa + data**, com função desempenhada, observação e autoria. É participação planejada naquele dia: não equivale a dedicação exclusiva, jornada completa, horas trabalhadas ou capacidade disponível.

O exemplo `Pessoa Exemplo | Montagem/Soldagem | Eixo THC 95 | segunda a quinta` gera quatro registros independentes. Outra tarefa na terça gera um quinto registro, sem substituir a primeira. Função desempenhada é um vínculo a `Funcao` e pode ser diferente da função principal do trabalhador; use o cadastro profissional adequado à atividade.

## Integridade e regras

- `UniqueConstraint(trabalhador, tarefa, data)` impede duplicidade exata no PostgreSQL. Mudar a função não cria outra alocação para a mesma tarefa/dia; edite a existente.
- Datas devem estar dentro do período previsto da tarefa, inclusive início e fim. Tarefas pendentes ou em andamento aceitam alocações; concluídas/canceladas precisam ser reabertas.
- Trabalhador inativo não recebe novas alocações nem alterações nas existentes. Reativação permite correções; exclusão de um dia continua possível com permissão de exclusão.
- Inativar trabalhador ou encerrar tarefa preserva alocações já registradas. Essas operações não apagam nem redistribuem pessoas automaticamente.
- Replanejar uma tarefa não pode deixar alocações fora de seu novo período. Primeiro corrija/remova os dias incompatíveis ou mantenha um período que os abranja.
- Trabalhador, tarefa, função e autores usam `PROTECT`: os cadastros referenciados não podem ser apagados enquanto houver vínculos.
- A função desempenhada é obrigatória; não existe vínculo obrigatório entre usuário do sistema e trabalhador. O setor principal do trabalhador pode ser diferente do setor da tarefa.

## Autoria e autorização

`criado_por`/`criado_em` preservam a criação; `alterado_por`/`alterado_em` registram a última alteração. O Admin preenche a autoria com `request.user`, ignorando valores de autoria enviados pelo cliente. Criador não é substituído em uma edição. As operações do Admin também usam seu log nativo, incluindo exclusões.

Criação, edição e remoção pelo modelo exigem `save(ator=usuario)` ou `delete(ator=usuario)`. O ator precisa estar autenticado e ativo e ter, respectivamente, `add_alocacao`, `change_alocacao` ou `delete_alocacao`. A consulta por serviço exige `view_alocacao`. O Admin exige adicionalmente acesso staff, como de costume.

Nesta entrega são usadas permissões globais nativas do Django. O filtro de setor é de consulta, não uma barreira de autorização. Perfis e restrições por setor continuam na issue #6; esta etapa não autoriza um piloto com segregação por setor.

## Operação com vários dias

No Admin, **Planejamento operacional → Alocações diárias → Alocar vários dias** permite escolher trabalhador ativo, tarefa aberta, função, primeiro/último dia e dias da semana. A seleção inclui os limites do período e pode atravessar semanas. O formulário limita cada operação a até 366 dias, para evitar seleções excessivas acidentais.

O serviço `alocar_dias` recebe uma lista explícita de datas e usa `transaction.atomic`: ou todos os registros são criados, ou nenhum. Data repetida na seleção, duplicata existente, dia fora do período ou outro erro reverte todo o lote. Não há sobrescrita silenciosa de alocações existentes.

As gravações bloqueiam as linhas de tarefas/trabalhadores durante a validação, e a alteração de prazo usa o mesmo bloqueio de tarefa. A constraint do banco reforça a unicidade, inclusive entre operações simultâneas.

```python
from datetime import date
from apps.planejamento.services import alocar_dias

registros = alocar_dias(
    ator=usuario_autenticado,
    trabalhador=trabalhador,
    tarefa=tarefa,
    datas=[date(2026, 11, dia) for dia in (2, 3, 4, 5)],
    funcao_desempenhada=funcao,
    observacao="Montagem do eixo",
)
```

Para corrigir quarta-feira, abra apenas sua alocação no Admin. Mudar observação/função/data ou excluir esse registro não altera segunda, terça e quinta. Exclusão remove o planejamento daquele dia; não é apontamento de produção executada. O histórico de tarefa continua existindo, mas não é um histórico de versões de cada alocação.

## Consultas e caminhos suportados

`consultar_alocacoes(ator=usuario, inicio=data_inicial, fim=data_final, setor_id=...)` retorna o intervalo inclusivo, com `select_related` para trabalhador, tarefa/setor, função e autores. O índice `(data, tarefa)` apoia consultas por período; as FKs e a chave única têm seus índices. A listagem do Admin oferece busca e filtros e também pré-carrega os vínculos.

O modelo usa `full_clean()` nas gravações suportadas e o serviço verifica permissão no servidor. Não use `bulk_create`, `bulk_update`, `QuerySet.update`, `QuerySet.delete` ou SQL direto como interface operacional: ignoram parte ou toda a validação, autoria e checagem de permissões. A exclusão em lote do Admin é uma exceção controlada, pois verifica a permissão no servidor e registra o log nativo.

## Roteiro de conferência

1. Aplicar `python manage.py migrate` e abrir o Admin com usuário administrativo.
2. Cadastrar dados fictícios e a tarefa **Eixo THC 95**, de 02/11/2026 a 20/11/2026.
3. Em **Alocar vários dias**, selecionar 02/11 a 05/11 e segunda a quinta: devem surgir quatro alocações.
4. Criar outra tarefa para a mesma pessoa na terça, 03/11: ambas devem permanecer.
5. Alterar ou remover somente a alocação de quarta, conferindo que os outros dias permanecem.
6. Repetir uma alocação existente: deve aparecer erro, sem duplicação nem lote parcial.
7. Tentar data fora do prazo, trabalhador inativo ou tarefa encerrada: o servidor deve rejeitar.
8. Conferir os autores e testar um usuário staff com apenas `view_alocacao`: pode consultar, mas não gravar pela tela normal ou de vários dias.

## Verificação automatizada

```bash
python manage.py check
python manage.py migrate --noinput
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test -v 2 --noinput
```

Os testes exercitam seleção multidiária, duas tarefas no mesmo dia, correção/remoção isolada, limite de período, duplicidade na aplicação e no banco, rollback, autoria, permissões, consulta sem N+1, formulários do Admin e concorrência real no PostgreSQL.

Fora do escopo: quadro semanal (issue #5), turnos, horários, horas-pessoa, controle de capacidade e equipes fixas. Nenhuma integração com o GTH Agents é criada.
