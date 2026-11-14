# Cadastros organizacionais — issue #2

## Objetivo

Manter a base mínima de setores, funções profissionais e trabalhadores para o planejamento operacional. Este módulo pertence exclusivamente ao OP-APP; não compartilha banco, usuários ou API com o GTH Agents.

## Modelo e regras

| Cadastro | Campos | Identidade e vínculos |
| --- | --- | --- |
| Setor | nome, descrição opcional, ativo | Nome único sem distinguir maiúsculas/minúsculas |
| Função | nome, descrição opcional, ativo | Nome único sem distinguir maiúsculas/minúsculas |
| Trabalhador | nome, setor principal, função principal, ativo | Identificado pelo ID; homônimos permitidos, inclusive no mesmo setor/função |

Todos começam ativos. Nome é obrigatório, com no máximo 150 caracteres após normalização Unicode NFC, remoção de espaços nas extremidades e redução de sequências de espaços/brancos a um espaço. A grafia e os acentos são preservados: não se tenta deduzir que nomes diferentes correspondem à mesma pessoa ou área.

Exemplo: `  Corte   Plasma ` é salvo como `Corte Plasma`. Cadastrar `CORTE PLASMA` depois é rejeitado. Um setor inativo ainda reserva seu nome: reative o cadastro existente em vez de duplicá-lo. Dois trabalhadores chamados `Pessoa Exemplo` são permitidos e aparecem com IDs diferentes nas opções do Admin.

Setor e função principal são obrigatórios. Função profissional (Soldador, Montador etc.) não é perfil de autorização. Trabalhador não possui vínculo obrigatório com o usuário Django e seu cadastro não cria conta nem exige login individual. O acesso ao Admin usa usuários e permissões nativos do Django; autorização por setor pertence à issue #6.

## Validação e persistência

O Admin valida por ModelForm. O `save()` dos modelos também chama `full_clean()`, para que criação e edição pelo ORM comum apliquem as mesmas regras. A unicidade de setor/função é reforçada por constraints `Lower(nome)` no PostgreSQL, inclusive contra disputas entre gravações concorrentes.

`bulk_create`, `bulk_update`, `QuerySet.update` e SQL direto ignoram `save()` e a normalização/validação Python. Não são o caminho de cadastro suportado nesta entrega. A constraint de unicidade no banco continua valendo, mas não substitui a normalização; futuras importações devem validar cada registro e tratar conflitos antes de gravar.

## Inativação e exclusão

- Inativar altera apenas `ativo`: preserva ID, dados e vínculos e pode ser revertido.
- Inativar um setor ou uma função não inativa trabalhadores em cascata. Os vínculos existentes continuam visíveis e editáveis, mesmo quando o cadastro relacionado está inativo.
- `PROTECT` impede excluir setor/função com trabalhadores vinculados, inclusive trabalhadores inativos. O Admin apresenta os vínculos que impedem a exclusão.
- Cadastros sem vínculos podem ser excluídos para corrigir erros. Para descontinuar um cadastro operacional, prefira inativação.
- Ainda não existem tarefas ou alocações. Quando forem criadas, suas referências a trabalhadores/setores deverão preservar o histórico, sem exclusão em cascata. Esta entrega não inventa um histórico de alocações nem registra versões da lotação principal; edições feitas no Admin usam o log nativo de alterações.

## Como usar no Admin

1. Aplicar a migração: `python manage.py migrate`.
2. Criar usuário administrativo, se necessário: `python manage.py createsuperuser`.
3. Iniciar o servidor e abrir `/admin/`.
4. Em **Organização**, cadastrar um setor fictício, por exemplo `Caldeiraria`, e uma função `Soldador`.
5. Cadastrar um trabalhador fictício, escolhendo setor e função principal.
6. Usar a busca e os filtros por ativo, setor e função. ID e nome são links de edição; o ID diferencia homônimos.
7. Desmarcar **Ativo**, salvar e conferir que o registro continua consultável pelo filtro de inativos.
8. Tentar excluir o setor vinculado e confirmar o bloqueio. Reativar o trabalhador sem criar outro ID.

Setores e funções têm busca por nome/descrição e filtro de ativo. Trabalhadores têm busca por nome, nome do setor e nome da função, com filtros para esses vínculos e ativo. A listagem carrega os vínculos com `select_related`.

## Verificação

```bash
python manage.py check
python manage.py migrate --noinput
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test -v 2 --noinput
```

A suíte inclui cenários de normalização, obrigatoriedade, duplicação no modelo e no banco, homônimos, proteção de exclusão, inativação/reativação e troca de lotação. As requisições de teste ao Admin exercitam cadastro, edição, validação, busca, filtros, proteção de exclusão e permissões nativas de consulta. A integração PostgreSQL é executada pelo workflow existente; os testes usam dados sintéticos.

Ficam fora desta entrega: tarefas, alocações, planejamento semanal, horas, produtividade, login de operários e integração externa.
