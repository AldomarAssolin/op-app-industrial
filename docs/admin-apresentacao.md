# Ajustes do Admin — issue #32 (24.1)

O Admin continua nativo. Uma extensão de `admin/base_site.html` carrega CSS próprio,
preserva os blocos do Django e acrescenta o link “Voltar à área de trabalho” junto à
identificação do produto. O link usa a mesma sessão e aponta para `/app/`; não aparece
no login ou em popups sem cabeçalho. A identificação do site é configurada no AdminSite.

A home principal recebe a classe `op-admin-home`. Os índices de apps (incluindo
Organização e Planejamento) recebem `op-admin-app-index`. Acima de 1024 px, seu conteúdo
usa grid com cadastros e Ações recentes, largura fluida limitada a 1280 px e margens
simétricas. Não usa o float/margem negativa do sidebar nessa largura. Índices por app são centralizados em uma coluna, limitada a 960 px, pois não têm
Ações recentes. Listagens e formulários não recebem essas alterações de distribuição. Abaixo desse breakpoint, fica
valendo o layout responsivo nativo; não há altura fixa.

O tema escuro usa cinza azulado, superfícies distintas e links menos saturados. A paleta
é aplicada a `data-theme=dark` e ao modo automático quando o sistema prefere escuro.
O claro explícito permanece com a paleta nativa mesmo nesse sistema. O seletor e o
script de tema do Django permanecem intactos. Não há dependência ou tema de terceiros.

## Verificação executada

40 testes relacionados passaram localmente com SQLite, incluindo carregamento da
extensão na home, índice de app, listagem, formulário e troca de senha; link de retorno
na mesma sessão; preservação do login, popups, scripts de tema, estáticos e autorização.
`collectstatic` e `git diff --check` passaram. A suíte PostgreSQL fica a cargo do CI.

Cálculo sRGB dos pares definidos: texto/fundo 12,87:1; texto secundário/superfície 7,93:1;
link/superfície 7,67:1; link/linha selecionada 5,28:1; link visitado/superfície 8,28:1;
cabeçalho 8,89:1; botão 7,72:1 e hover 5,92:1; borda/superfície 3,26:1. Os pares de
texto das mensagens de sucesso/aviso/erro também superam 4,5:1. Estes cálculos não
substituem inspeção do estilo computado, de todos os estados ou avaliação visual.

## Roteiro visual de referência e conferências específicas

- Conferir home em 1440 e 1920 px: conjunto centralizado e ações alinhadas, sem excesso
  de espaço entre nome e botões; testar também pouco ou nenhum histórico recente.
- Conferir também `/admin/organizacao/` e `/admin/planejamento/` em telas grandes:
  coluna centralizada sem espaço reservado para Ações recentes.
- Conferir 390 px, largura intermediária e zoom: cabeçalho/link de retorno sem cortes;
  home utilizável e comportamento anterior de listagens/formulários preservado.
- Conferir claro, escuro e automático (preferência do sistema clara e escura), incluindo
  troca após recarregar. O claro explícito deve prevalecer sobre o sistema escuro.
- Conferir links/hover/visitados, seleção, mensagens, inputs e ações de formulário.
- Navegar por teclado, conferir foco visível e retorno a `/app/` a partir de home,
  listagem, edição e troca de senha.

Não há migração, variável de ambiente nova ou alteração de permissões. O deploy precisa
incluir os templates do projeto e executar collectstatic, como já previsto na imagem.
Manex confirmou aceite visual local, inclusive do complemento nos índices, e depois
validação em produção. Não há inspeção visual independente do assistente. Larguras exatas,
zoom, teclado e todas as combinações de tema/estados do roteiro não foram confirmados
individualmente; continuam como conferências específicas, sem reabrir a implementação.

## Complemento do aceite

Manex aprovou visualmente a implementação inicial e identificou o mesmo problema nos
índices Organização e Planejamento. O ajuste foi ampliado a esses índices; a conferência
visual desse complemento foi aprovada pelo operador antes do merge da PR #33. O teste de integração cobre os dois
endereços e verifica que listagens/formulários não recebem a classe dos índices.


## Links de consulta, histórico e turnos da tarefa

Campos somente de leitura preservam o nome do cadastro relacionado, mas só exibem link quando o usuário pode consultar ou editar esse destino. Exemplo: o Coordenador vê o autor no histórico sem receber um link para a administração técnica de usuários. O Líder vê o nome do setor sem um link para um cadastro fora das suas permissões. O acesso direto continua bloqueado pelo servidor.

O erro 403 apresenta orientação amigável e caminhos para a área de trabalho e administração, mantendo o status HTTP 403. Não são exibidos detalhes de exceção ou dados do registro negado.

O histórico mostra os nomes das atividades, escapados como texto, preservando os IDs e nomes na fotografia JSON armazenada. Não altera o histórico existente.

Turnos tarefas deve mostrar todas as participações autorizadas, ativas ou inativas, já no GET inicial do Coordenador e dos perfis administrativos. O Líder não recebe edição desse bloco. A consulta do inline aplica explicitamente o escopo; não usa a checagem genérica do InlineModelAdmin sem a tarefa pai, que ocultava registros do Coordenador. Duplicidades continuam inválidas e não criam novos vínculos.

### Manutenção dos templates do Admin

`templates/admin/includes/fieldset.html` e `templates/admin/edit_inline/tabular.html` acompanham a estrutura do Django 5.2 e substituem apenas a renderização do valor readonly pela tag `readonly_com_acesso`. Ao atualizar Django, comparar os templates com a nova versão, mantendo acessibilidade e os testes de links por perfil. Não há alteração global das classes internas do framework.
