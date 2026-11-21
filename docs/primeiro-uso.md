# Orientação do primeiro uso — issue #25

## Comportamento

A entrada `/app/` apresenta um próximo passo, reavaliado a cada consulta, sem assistente
obrigatório ou bloqueio dos atalhos existentes. A sequência é configuração de setor e
funções, trabalhadores ativos, tarefas pendentes/em andamento, alocações e consulta da
semana. Não cria registros nem altera grupos, permissões ou regras operacionais.

Conta sem setor recebe orientação de acesso; Administrador sem setores pode receber o
atalho de configuração se tiver permissão e acesso ao Admin. Falta de permissão de
leitura necessária à orientação não é apresentada como ausência de cadastro.

Ações de criação exigem a política existente de autorização, acesso staff para destinos
do Admin e escopo aplicável. Líder sem função recebe orientação ao Administrador; sem
equipe ativa, ao Coordenador/Administrador. Consulta não recebe ações de gravação, mesmo
com permissão avulsa incompatível com a política do perfil.

## Escopo e limites

Trabalhadores, tarefas e alocações são consultados apenas nos setores autorizados.
No quadro, a orientação respeita também o setor selecionado e a semana solicitada.
Funções são um cadastro compartilhado já existente: sua existência só é consultada
quando a conta tem leitura desse cadastro. Não são exibidos nomes ou contagens globais.
A orientação não exige funções/setores ativos como uma regra nova: mantém as condições
dos formulários e serviços atuais; trabalhadores inativos e tarefas encerradas não
indicam prontidão para novas alocações.

Na entrada, uma base com alocações em outros períodos distingue semana atual sem
planejamento de ausência total de alocações. Uma conta com vários setores recebe uma
orientação agregada, não uma auditoria de completude de cada setor ou de compatibilidade
de todas as pessoas/tarefas. As validações de cada operação continuam no backend.

Nas listas de trabalhadores, tarefas e alocações do Admin:

- Sem registros no escopo: mensagem contextual e orientação do próximo passo.
- Sem resultados da busca/filtros, mas com registros no escopo: orientação para limpar
  a busca e os filtros. Nunca considera registros de setores fora do acesso.
- Com resultados: preserva a listagem sem acrescentar etapas obrigatórias.

O formulário de vários dias mostra a orientação quando faltam pré-requisitos, preservando
formulário e validação. No quadro vazio, diferencia setor filtrado sem alocações de semana
sem alocações em qualquer setor permitido, além do aviso de falta de vínculo quando cabe.
Parâmetro de setor indevido mantém a rejeição existente. Esta entrega não antecipa o novo
fluxo de planejamento da #26 nem a preservação de contexto entre ações da #27.

## Verificação executada

64 testes relacionados passaram localmente em SQLite, incluindo 12 novos testes de
progressão, perfis, escopo, ausência de vínculo/permissão, inativos, tarefas encerradas,
semana/filtro, listas vazias e formulário de planejamento. Collectstatic foi executado.
Suíte completa PostgreSQL e imagem são verificadas no CI.

## Roteiro de aceite visual e de uso

- Como Líder, testar falta de função, depois falta de trabalhador ativo; conferir a
  orientação e ausência de botões de cadastro proibidos.
- Como Coordenador, conferir o cadastro permitido de trabalhadores; como Administrador,
  conferir configuração de setor/função; como Consulta, manter somente leitura.
- Completar a sequência com dados fictícios; a entrada deve reavaliar o próximo passo
  e manter os atalhos acessíveis a qualquer momento.
- Abrir listas vazias de equipe, tarefas e alocações; depois inserir registros e fazer
  uma busca sem resultado. Conferir a distinção e o link Limpar busca e filtros.
- Conferir quadro vazio, outra semana e setor sem alocações; conferir conta sem vínculo.
- Em desktop e celular, testar leitura, quebra da sequência, zoom, Tab/Shift+Tab e foco
  dos links, nos temas existentes. Orientação não aparece na impressão do quadro.

Não houve inspeção visual independente nem deploy nesta entrega. Não há migração ou
nova variável de ambiente; a imagem deve coletar os estáticos como já faz atualmente.
