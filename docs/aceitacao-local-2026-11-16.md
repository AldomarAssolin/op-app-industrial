# Aceitação local de perfis — issue #6

Data: 16/11/2026 (America/Sao_Paulo).
Ambiente: aplicação local em http://127.0.0.1:8000, navegador do usuário.
Execução: assistente pela interface; usuário realizou os logins e definiu as senhas.
Commit local: não confirmado pela interface; não atribuir os resultados a um SHA sem conferir o checkout. A referência do repositório conhecida durante a preparação era a PR #14, merge 5227c81be174b3b1d50d5e4b86d300b4b9edb92e.
Resultado: cenários executados aprovados; aceitação integral e piloto permanecem pendentes.

## Preparação e limites

Foram reutilizados os setores locais Caldeiraria (A, ID 1) e Inox (B, ID 3). Eles não foram criados como setores sintéticos para esta execução, diferentemente da preparação ideal do roteiro. Nenhum cadastro operacional preexistente foi alterado; as gravações de teste usaram somente registros identificados por QA-ACEITACAO.

Contas utilizadas: Líder alex_dick, Coordenador matheus_martins, Consulta qa_consulta, Administrador operacional qa_admin_oper e superusuário de preparação Aldomar. Consulta foi configurado com staff e grupo Consulta, sem superusuário, vinculado apenas a Caldeiraria. Administrador operacional foi configurado com staff e grupo Administrador, sem superusuário. Nenhuma senha integra esta evidência.

O teste comprova o comportamento observado, não uma auditoria completa das associações prévias de Líder e Coordenador. Não foram acrescentadas permissões individuais indevidas para testar a defesa adicional.

## Evidências por perfil

| Perfil/cenário | Resultado observado |
| --- | --- |
| Consulta: listagem de tarefas e trabalhadores | Apenas Caldeiraria; pessoa B e tarefa B ausentes |
| Consulta: tarefa A | Campos somente leitura e ausência de salvar |
| Consulta: detalhe direto de tarefa B, alocação B e trabalhador B | Objeto ocultado com mensagem de inexistência; nenhum detalhe B exibido |
| Consulta: URL de criação de tarefa e gestão de usuários | 403 Forbidden |
| Consulta: quadro e filtro de setor B na URL | Apenas Caldeiraria nas opções; filtro setor=3 rejeitado com “Selecione um setor permitido.” |
| Administrador operacional: lista de tarefas | Caldeiraria, Inox e Montagem Geral visíveis |
| Administrador operacional: tarefa B | Alteração Pendente → Em andamento salva; histórico 15 identifica qa_admin_oper |
| Administrador operacional: trabalhador B e quadro | Formulário de edição disponível; quadro mostra a alocação sintética B |
| Administrador operacional: usuários, grupos e vínculos | Três URLs de listagem retornam 403 Forbidden |
| Líder: menu e opções de alocação | Funções/Trabalhadores para leitura, Tarefas/Alocações para escrita; opções restritas a A |
| Líder: Setores e criação de trabalhador | URLs retornam 403 Forbidden |
| Líder: alocação B por URL direta | Objeto ocultado |
| Líder: tarefa A e histórico | Criação e mudanças Pendente → Em andamento → Cancelada registradas com alex_dick; tentativa direta Pendente → Concluída rejeitada |
| Coordenador: trabalhadores | Apenas A na lista; setor principal oferece apenas Caldeiraria |
| Coordenador: inativação/reativação da pessoa A | Ambas salvas; tentativa de nova alocação enquanto inativa rejeitada |
| Coordenador: trabalhador B por URL direta | Objeto ocultado |
| Coordenador: criação de setor e gestão de vínculos | 403 Forbidden |
| Coordenador: tarefa sintética 8 | Cancelamento e reabertura salvos; alocação durante cancelamento rejeitada |
| Logout | Após sair, quadro semanal exige login |

## Alocações e quadro

1. Líder criou lote de 16 a 19/11: quatro alocações, IDs 14–17, pessoa A/tarefa 6/função sintética; autoria alex_dick.
2. Lote 19–20/11 rejeitado por duplicidade do dia 19. Lista manteve quatro registros sintéticos; nenhum dia 20 criado.
3. Lote 27–30/11 rejeitado por ultrapassar conclusão da tarefa (27/11). Lista manteve os mesmos quatro registros, inclusive sem dia 27 parcial.
4. Segunda tarefa A (8) na terça, 17/11, criada como alocação 19. Quadro preservou as duas tarefas no mesmo dia.
5. Observação da alocação 16, quarta 18/11, alterada isoladamente. Quadro preservou a observação original de segunda, terça e quinta.
6. Alocação 20 em 23/11 criada. Navegação à próxima semana exibiu o registro.
7. Tentativa de reduzir prazo da tarefa 6 para 18/11 rejeitada por excluir alocações existentes do período.
8. Tentativa de alocação em 24/11 com pessoa A inativa rejeitada: “Trabalhador inativo não pode receber alocações.”
9. Tentativa de alocação em 24/11 na tarefa 8 cancelada rejeitada: “Reabra a tarefa antes de criar ou alterar alocações.”

Lacunas numéricas nos IDs são compatíveis com sequências do banco e não foram usadas como comprovação de rollback; a comprovação veio da listagem após cada erro.

## Estado final dos registros de teste

| Registro | Estado deixado |
| --- | --- |
| Função 4 | QA-ACEITACAO - Montagem/Soldagem |
| Trabalhador 5 / A | Ativo, Caldeiraria |
| Trabalhador 6 / B | Ativo, Inox |
| Tarefa 6 / A | Pendente, 16–27/11 |
| Tarefa 7 / B | Em andamento, 16–27/11 |
| Tarefa 8 / segunda A | Pendente, 16–27/11, após reabertura |
| Alocação 13 | Pessoa B/tarefa B, 17/11, criada na preparação pelo superusuário |
| Alocações 14–17 | Pessoa A/tarefa A, 16–19/11 |
| Alocação 19 | Pessoa A/segunda tarefa A, 17/11 |
| Alocação 20 | Pessoa A/tarefa A, 23/11 |

Registros e contas de teste permanecem no banco; não houve limpeza por exclusão. Sessão foi encerrada ao terminar.

## Pendências para aceitação integral

- Confirmar o SHA efetivamente executado no checkout local.
- Coordenador: criar novo trabalhador sintético de A e testar transferência enviada para B; foi testada edição/inativação, e B estava ausente das opções, mas nenhum POST de transferência forjado foi enviado.
- Líder: enviar IDs B adulterados no POST individual e multidiário; ausência das opções e URLs protegidas não substitui esse teste.
- Consulta: POSTs de criação, edição e exclusão; leitura somente e GET 403 foram conferidos, sem POSTs forjados.
- Repetir a matriz com permissões individuais indevidas, se exigido para a aceitação manual da defesa adicional.
- Exclusão de alocação e proteção de exclusão de tarefa não foram exercitadas nesta sessão.
- Cookies, CSRF, sessão e HTTPS no host real do piloto; este teste usou HTTP localhost. DEBUG=True foi observado na página 404 local, sem constituir configuração válida de piloto.
- Responsável pelo piloto, backup e restauração em banco separado, configuração de proxy/hosts/cookies e check --deploy.

Os testes automatizados anteriormente informados não foram reexecutados nesta sessão. Não considerar sua cobertura equivalente às pendências manuais. Manter a issue #6 aberta.
