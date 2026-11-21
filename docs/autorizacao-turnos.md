# Autorização por setor e turno — #36

## Estado e decisões

Implementação sobre a #35; habilitação opcional, desabilitada por padrão. Sem implantação
ou merge por esta entrega. Validar as duas PRs juntas em ambiente local com dados sintéticos.

| Perfil | Leitura e operação com turnos habilitados |
| --- | --- |
| Coordenador | Todos os turnos dos setores pelos quais responde; mantém equipe, dados gerais e vínculos de Líder conforme permissões. |
| Líder | Somente pares setor/turno explicitamente ativos e com acesso básico ao setor. Pode ter múltiplos pares. |
| Consulta | Somente leitura em todos os turnos dos setores previamente autorizados. |
| Administrador operacional | Mantém o alcance global de dados; não recebe gestão de usuários, grupos ou vínculos de Líder. |
| Superusuário técnico | Configuração inicial de contas, responsáveis e recuperação; exceção técnica global. |

Consulta combinado com Líder não amplia o escopo do Líder. Coordenador combinado com
Líder opera como Coordenador nos setores sob sua responsabilidade e como Líder nos demais
pares autorizados. Ter o grupo Coordenador, sozinho, não concede setores.

Cada setor admite no máximo um responsável, por restrição única no banco. Um setor em
preparação pode ficar sem responsável: não concede acesso ao Coordenador até a configuração.
A substituição é atômica, feita pelo superusuário técnico e auditada; não é autoatribuição.
O Coordenador mantém vínculos de Líder apenas em seu setor, sem editar contas, grupos,
permissões nem os próprios setores. O acesso básico `UsuarioSetor` e o perfil Líder são
pré-requisitos preparados pelo responsável técnico; o vínculo não promove uma conta.

## Tarefas compartilhadas e encerramento

O Líder continua criando tarefas novas no próprio setor, com turno de operação explícito.
Depois da criação, título, descrição, setor, período e observações gerais ficam reservados
ao Coordenador. O Líder altera alocações autorizadas e acrescenta observações do seu turno.
Observações por turno são registros anexados com autor/data, sem sobrescrever outro turno.
O Coordenador vê todas e mantém as observações gerais. A observação da alocação continua
pertencendo ao respectivo registro de trabalhador/data/turno.

A participação em uma tarefa pode ser preparada pelo Coordenador no formulário da tarefa;
alocações existentes do turno também determinam participação. Apenas pertencer ao setor
não disponibiliza uma tarefa exclusiva de outro turno. A criação pelo Líder já registra
sua participação. Históricos sem turno de operação não ficam visíveis ao Líder.

Transições do Líder: Pendente → Em andamento → Concluída. Cancelamento e reabertura são
responsabilidade do Coordenador. Concluir exige ausência de alocações na data operacional
de hoje **ou posterior** em turno diferente do turno da ação, incluindo legado sem turno.
Mesmo que o Líder possua dois vínculos, deve selecionar o turno da ação; o outro ainda
bloqueia. A referência de calendário é America/Sao_Paulo, sem inferência pelos horários.
A verificação usa bloqueio da tarefa e é refeita ao gravar. Se rejeitada, preserva status,
histórico e alocações e orienta procurar o Coordenador sem revelar o planejamento oculto.

## Configuração local e aceite

Usar uma cópia local descartável; não reutilizar credenciais de produção.

1. Atualizar para a branch da PR #36 (ela inclui a base da #35), ativar o virtualenv e
   executar `python manage.py migrate` e `python manage.py configurar_perfis`.
2. Definir `OP_APP_TURNOS_ENABLED=True` no ambiente local e reiniciar o servidor.
   A opção continua False em instalações que não optarem pela nova operação.
3. Como superusuário técnico, preparar contas ativas e grupos, setores e acessos básicos
   `UsuarioSetor` para Líder/Consulta. Não tornar contas operacionais superusuárias.
4. Em Organização → Responsáveis por setor, associar o Coordenador de cada setor.
5. Como Coordenador, criar os vínculos ativos de Líder para T1/T2/T3 no próprio setor.
6. Na criação do trabalhador, escolher opcionalmente o turno inicial (vigente hoje).
   Sem seleção, permanece Turno não informado. Na edição, a seção Atualizar turno habitual
   permite iniciar a revisão com vigência. Para legado futuro,
   marcar explicitamente a classificação após revisar o conjunto. Ver `turnos.md`.
7. Preparar participação dos turnos nas tarefas e alocações sintéticas. Conferir `/app/`,
   listas, opções de formulário, busca, URLs diretas, quadro e impressão.

Aceite mínimo:

- Líder T1 vê e altera apenas o permitido; T2/T3 e outro setor não aparecem em listas,
  opções, busca, quadro, impressão ou observações; URLs e POST adulterado são rejeitados.
- Coordenador vê T1/T2/T3 do próprio setor, mantém vínculos e não acessa outro setor.
- Conceder segundo vínculo permite o segundo turno; inativar revoga inclusive formulário
  já aberto. Manutenção de vínculos, substituição de responsável e participação de tarefa
  preservam autoria e trilha de alteração.
- Líder cria tarefa, mas não altera seus dados gerais depois; observações ficam separadas.
- Iniciar/concluir sem planejamento de outro turno funciona; planejamento de hoje/futuro
  em outro turno bloqueia e preserva os dados. Cancelar/reabrir exige Coordenador.
- Troca de habitual transfere o lote futuro revisado; conflito, alteração após revisão ou
  revogação rejeitam tudo. Uma pessoa/data não admite dois turnos, mesmo em tarefas distintas.
- Ausência de vínculo e Turno não informado não concedem acesso ao Líder. Coordenador
  recebe orientação para classificar equipe. Consulta não grava nem com permissão isolada.

O cadastro de trabalhadores usa habitual na data operacional atual; seletores de alocação
usam a data informada (início no formulário multidia). Registros de alocação/histórico usam
seu turno gravado, preservando a referência anterior às mudanças de habitual.

## Verificação técnica e reversão

`test_autorizacao_turnos.py` cobre escopos, combinações de grupos, múltiplos vínculos,
revogação, POST, formulários, CSRF, observações e encerramento. Três casos exigem PostgreSQL:
encerramento versus nova alocação, substituição concorrente de responsável e revogação
concorrente com gravação. Somam-se aos testes de domínio/migração/concorrência da #35.

Operações autorizadas travam a conta do ator antes das tarefas/trabalhadores; manutenção
de vínculo/responsável também trava contas para serializar revogação/substituição.
Atualização direta por SQL, QuerySet.update ou bulk_create fora dos serviços não constitui
API autorizada. As permissões novas do Coordenador são somente view/add/change de vínculo
de Líder e consulta dos históricos de acesso e mudança de habitual; não há gestão geral
de contas. Os testes devem ser executados em PostgreSQL no CI antes de aceite.

As migrações não inferem responsáveis, vínculos, turnos habituais ou participação de legado.
A reversão das novas migrações recusa apagar dados de responsabilidade/vínculo/auditoria,
participação, observações por turno ou histórico já classificado. Após uso, não basta voltar
imagem nem desabilitar a opção (isso restaura o escopo anterior por setor): recuperar imagem
e banco compatíveis em cópia e decidir a reversão operacional explicitamente. Obter backup
verificado e autorização de implantação antes de ativar em produção.

## Correções da revisão da PR

Mover uma tarefa exige responsabilidade no setor original e no destino. Uma conta que é
Coordenador em A e apenas Líder em B não pode trazer uma tarefa de B para A para obter
edição de dados gerais ou cancelar/reabrir. O teste verifica preservação do setor, título,
status e histórico na rejeição.

Ao abrir a edição de alocação, as opções de trabalhador usam a data do registro, não o
habitual de hoje. Testes GET/POST cobrem alocação passada e futura após mudança de habitual,
com edição autorizada de observação sem perder o trabalhador selecionado. As URLs dos
novos históricos também ficam fechadas quando a opção de turnos está desabilitada.

## Identificação do trabalhador na alocação

Nos seletores de alocação diária e multidia, o trabalhador aparece como `Nome — T1`, sem
ID técnico. Sem habitual vigente, aparece `Nome — Turno não informado`. A identidade usada
para gravar continua sendo a chave do trabalhador; a identificação nas outras telas não muda.
Ao mudar a data (ou o primeiro dia no multidia), o formulário consulta novamente as opções
permitidas, atualizando os turnos sem apagar os demais campos digitados. No multidia, cada
dia continua sendo validado ao salvar; o rótulo usa o início. Sem data, a referência é hoje.


## Cadastro inicial, edição e visão da equipe

O turno inicial do trabalhador é opcional e começa na data operacional de hoje. Cadastro e
primeiro evento de habitual são gravados juntos, com autoria; falha reverte ambos. Sem
seleção, não há evento e a apresentação é Turno não informado. Administrador operacional
pode informar o turno na criação conforme sua permissão de cadastro; isso não concede
permissão de troca futura nem gestão de vínculos.

Na página de edição, Coordenador responsável e superusuário iniciam a troca pela seção
Atualizar turno habitual. A revisão continua exibindo o lote futuro antes da confirmação,
com as mesmas verificações e atomicidade. Ao confirmar, retorna ao trabalhador. Alterações
do cadastro devem ser salvas antes de iniciar a revisão. Não se sobrescreve o turno por um
select comum ao salvar os dados cadastrais. Eventos continuam cronológicos: vigência nova
posterior à última registrada; não há retificação ou remoção do histórico nesta entrega.

A edição exibe histórico somente leitura (vigência, origem/destino, autor, data e quantidade
transferida) ao Coordenador autorizado, Administrador e superusuário. A lista de trabalhadores
oferece a esses perfis um filtro de turno habitual vigente **hoje**, incluindo Turno não
informado, preservando o escopo de setores. Mudanças futuras não antecipam esse filtro.
