# Referências de turno — preparação da issue #35

## Estado da entrega

A #35 prepara domínio, migração e revisão/transferência. A #36 acrescenta autorização
por setor/turno, disponível por opt-in. `OP_APP_TURNOS_ENABLED=False` permanece o padrão;
True passa a permitir inicialização. Isso não configura contas nem autoriza implantação.

Consultar [autorizacao-turnos.md](autorizacao-turnos.md) para configuração, regras e aceite
conjunto. Sem responsabilidade/vínculo explícito, Coordenador/Líder não recebem acesso
operacional ao ativar a opção. A #26 e os filtros da #27 dependem desse aceite.

## Domínio preparado

TURNOS contém T1, T2 e T3 como identificações estáveis. Horários são informativos:
T1 07h18–17h18; T2 17h–02h; T3 23h–07h, marcado como aproximado. Não há cálculo de horas,
intervalos, escala, capacidade ou sobreposição por relógio. Administrador técnico pode
editar referências/inativar quando a operação for habilitada; não renomear ou excluir
identificações. As permissões adicionais da #36 são documentadas no roteiro de autorização.

A data da alocação permanece a data operacional de início do turno. A referência de
calendário da troca/habitual é America/Sao_Paulo; não usar mudança de dia UTC para impedir
uma troca ainda datada de hoje no Brasil. Os horários não determinam o turno escolhido.

O turno habitual do trabalhador é derivado de mudanças registradas por vigência, sem
necessidade de tarefa agendada à meia-noite. Sem mudança vigente, é Turno não informado.
Uma mudança futura não altera o turno habitual de hoje. O turno da alocação é um registro
independente, validado contra o habitual vigente na data planejada.

Mesma pessoa/data operacional só admite um turno, inclusive entre tarefas/setores;
tarefas diferentes no mesmo turno permanecem possíveis. A unicidade exata já existente
continua válida. Validação e bloqueio da linha do trabalhador serializam gravações pelos
modelos/serviços; escrita direta por SQL, update/bulk_create fora dos serviços não é API
suportada e pode violar invariantes. Turno é obrigatório e ativo em novas alocações
quando a operação estiver habilitada, e deve corresponder à referência vigente.

## Troca revisada pelo Coordenador

O serviço exige usuário ativo, grupo Coordenador, permissão de alterar trabalhador e
responsabilidade explícita no setor. O superusuário técnico pode executar a recuperação/configuração inicial; o Administrador operacional não ganha essa exceção.
Quando houver transferência, exige também alteração de alocações e acesso aos setores de
todas as tarefas afetadas, sem revelar detalhes de outros setores.

A tela preparada está em Trabalhadores → Revisar troca de turno. Etapas:

1. Informar T1/T2/T3 e data de vigência a partir de hoje (data operacional).
2. Revisar todo o conjunto de alocações com data maior ou igual à vigência.
3. Confirmar; token assinado vincula usuário, trabalhador, destino, vigência e resumo do
   estado revisado. Expira em 30 minutos e não substitui nova conferência de acesso/estado.
4. Revalidar e transferir o conjunto em uma transação. Mudança após revisão, falta de
   acesso, trabalhador inativo, turno inativo ou tarefa encerrada rejeitam a operação.

O serviço bloqueia tarefas antes do trabalhador, como a gravação de alocações. Inclusões
ou remoções depois da revisão invalidam o resumo. Duas tarefas do mesmo dia são movidas
juntas; falha em qualquer registro reverte o evento e todo o conjunto. A remoção pelo
Admin também utiliza a política de bloqueios dos serviços.

Mudanças são anexadas cronologicamente: nova vigência deve ser posterior à última
registrada. Não há edição/exclusão de eventos nem retorno automático de troca temporária.
O retorno ao turno anterior é outra mudança explícita com vigência posterior. Nesta
entrega não há correção/antecipação de uma mudança futura já registrada; revisar bem
antes de confirmar e tratar necessidade de retificação como evolução com auditoria.

## Legado e histórico

A migração cria as referências, mas não classifica trabalhadores nem alocações existentes.
FK de turno em alocações antigas permanece nula: Turno não informado. Registros anteriores
à vigência não são transferidos ou classificados pelo serviço.

Alocações futuras sem turno só são classificadas com a opção explícita de classificação
do legado e revisão completa pelo Coordenador. A confirmação registra a classificação;
não é inferência pelo horário ou pelo setor. Sem essa opção, a troca é rejeitada. Uma
alocação sem turno na mesma pessoa/data também impede novas inclusões nesse dia até a
regularização. O legado passado continua preservado/não classificado nesta etapa.

Mudanças de habitual e de referência de horário não reescrevem alocações anteriores.
Histórico de turno da alocação guarda marcador, pessoa, tarefa, data e autoria; permanece
mesmo após remover a alocação. Não afirma reconstituir o horário de referência antigo.
Esses eventos são anexados pelos serviços, sem edição direta no Admin.

## Testes e aceite

26 testes novos foram preparados: referências, calendário brasileiro, vigência futura,
transferência conjunta, revisão alterada/expirada/adulterada, reenvio, revogação de acesso,
rollback, papel/setor, legado explícito, inativos/encerradas, unicidade, histórico,
formulários/quadros e migração. O teste de configuração passou a validar o opt-in da #36. Três casos exigem PostgreSQL:
confirmações simultâneas, turnos distintos para a mesma pessoa/data e exclusão em lote
concorrente com edição entre tarefas. Os demais passaram
localmente em SQLite; PostgreSQL e suíte completa são conferidos no CI.

Validação visual e de uso dos caminhos preparados ocorrerá em ensaio sintético junto
com a #36, antes de qualquer ativação em produção. A cobertura adicional de isolamento
e encerramento compartilhado está em `test_autorizacao_turnos.py`.

## Migração e reversão

Antes de futura implantação autorizada, obter backup verificado, conferir versão executada
e ensaiar em banco isolado. As migrações adicionam tabelas e uma FK opcional, preservando
legado; conferir contagens, conteúdo e ausência de classificação automática.

Com turnos desabilitados e sem dados classificados, a versão anterior deve continuar
compatível com as colunas adicionais. Ensaiar reversão primeiro na cópia do banco. A
reversão de planejamento 0004 recusa retirar estruturas se existirem classificação ou
histórico de turnos, para não apagá-los. Depois da ativação futura, NÃO voltar só a imagem
antiga: ela não conhece os novos invariantes. Usar recuperação conjunta de imagem/banco
validada em cópia e decisão operacional explícita, considerando registros posteriores.
Nenhum deploy ou reversão foi executado por esta entrega.

## Correção após revisão

A revisão Codex identificou risco de deadlock na exclusão em lote. A operação passou a
bloquear todas as tarefas, depois trabalhadores e alocações em ordem global, revalidando
a seleção. A ação do Admin envolve a exclusão e seus logs na mesma transação e apresenta
erro de seleção alterada sem confirmar remoção parcial. Um teste PostgreSQL reproduz
a exclusão B→A concorrente com edição A→B, preservando a política de bloqueios.
