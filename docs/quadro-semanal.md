# Quadro semanal — issue #5

## Objetivo e acesso

O quadro em `/planejamento/semanal/` consulta as alocações existentes. Não há entidade `PlanejamentoSemanal` nem cópia dos registros por semana. O link **Quadro semanal** também está na listagem de alocações do Admin.

É necessário estar autenticado, ativo e possuir `planejamento.view_alocacao`. Usuário anônimo é encaminhado ao login nativo do Admin; usuários que usam esse login precisam de `is_staff`. A tela é apenas GET e não cria/edita registros.

## Escopo da consulta

- Superusuários consultam todos os setores.
- Para os demais usuários, o administrador cadastra os setores permitidos em **Organização → Acessos de usuários a setores** (`UsuarioSetor`). O vínculo é independente de `Trabalhador` e de sua lotação.
- Permissão de consulta sem vínculo de setor resulta em quadro vazio e nenhuma opção de setor. O vínculo sozinho, sem `view_alocacao`, não concede acesso.
- As opções do filtro e a consulta de alocações usam o mesmo escopo no servidor. Sem filtro explícito, aparecem somente os setores autorizados. Alterar o parâmetro de setor na URL não amplia o acesso; opção não permitida resulta em erro de formulário (HTTP 400), sem nomes de setores/atividades restritos.
- O serviço `consultar_alocacoes` também aplica esse escopo. Filtro explícito de setor não autorizado é rejeitado com `PermissionDenied`.

O vínculo mínimo foi antecipado da issue #6 para satisfazer o critério de consulta autorizada. A definição de grupos Administrador/Coordenador/Líder/Consulta e a extensão do escopo a todos os formulários, listagens, detalhes e gravações do Admin continuam na issue #6. O Admin de tarefas/alocações ainda usa permissões globais; não conceda esses acessos a pessoas que devam ficar restritas por setor antes dessa etapa. Esta entrega não representa liberação para piloto segregado por setor.

## Semana, linhas e dias

Selecionar qualquer data determina a semana de segunda a domingo; sem parâmetro usa-se a data atual do fuso configurado no Django. O cabeçalho exibe o intervalo completo e os links anterior/próxima avançam sete dias, preservando setor e opção de fim de semana.

Cada linha reúne **ID do trabalhador + ID da função desempenhada + ID da tarefa**. Duas tarefas no mesmo dia aparecem em linhas distintas; funções diferentes também. Nomes homônimos não são mesclados e o ID do trabalhador aparece na tela.

As colunas padrão são segunda a sexta. Marcar **Mostrar sábado e domingo** exibe sete dias. Se houver alocações autorizadas no sábado/domingo, essas colunas aparecem automaticamente, evitando ocultação de registros. Dados de setores não autorizados não influenciam essa expansão.

As células marcam somente dias com alocação efetiva e mostram sua observação. Dias vazios não significam disponibilidade ou ausência. Uma tarefa pode começar antes e terminar depois da semana; seu período previsto completo é exibido, mas não gera marcas fictícias nos dias sem alocação. Trabalhador inativo e tarefa encerrada continuam aparecendo quando possuem alocações na semana consultada.

## Cenário de referência

Com `Aldomar | Montagem/Soldagem | Eixo THC 95` alocado de segunda a quinta, aparecem quatro células preenchidas na mesma linha. Uma segunda tarefa na terça cria outra linha para o mesmo trabalhador, preservando ambas.

Se Eixo THC 95 começou em 26/10/2026 e terminará em 20/11/2026, alocações em 30/10, 04/11 e 09/11 aparecem nas respectivas semanas durante a navegação. Não é necessário cadastrar novamente a tarefa nem gerar uma entidade de semana.

## Apresentação e impressão

A tela usa Django Templates, tabela com cabeçalhos acessíveis, foco visível e rolagem horizontal para telas pequenas. A ação **Imprimir** usa a impressão do navegador; o CSS de impressão remove controles, repete cabeçalhos e prepara orientação paisagem. Não é exportação de planilha ou relatório de produção.

Roteiro visual: abrir o quadro com dados sintéticos, conferir duas tarefas na terça, navegar para a semana seguinte e voltar, testar seleção de setor, sábado/domingo, tela pequena e a prévia de impressão. O ambiente de implementação validou o HTML por requisições Django, mas não conseguiu iniciar Chromium para captura visual; a conferência visual no navegador local permanece documentada, sem ser declarada aprovada.

## Verificação

```bash
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test -v 2 --noinput
```

Os testes cobrem referência segunda–quinta, tarefas simultâneas, funções/homônimos, cruzamento de semanas, fim de semana, filtros, ausência de vínculo, acesso negado, manipulação de setor na URL, navegação, limites de datas, estado vazio, escape de conteúdo e consulta sem N+1. O CI executa a suíte completa no PostgreSQL 17.

Fora do escopo: Gantt, arrastar/soltar, Excel, apontamento de produção, horas e produtividade. Nenhuma integração com GTH Agents ou função de segurança de máquinas foi acrescentada.
