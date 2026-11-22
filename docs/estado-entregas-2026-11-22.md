# Estado das entregas e pendências — 22/11/2026

## Fonte e alcance do registro

Reconciliação autorizada por Manex após revisão das issues, PRs e documentação. Os aceites
manuais e as evidências operacionais foram fornecidos pelo operador nesta conversa.
Não constituem inspeção independente do servidor ou comprovação de itens não relatados.
Os registros históricos descrevem a fase em que foram escritos; esta consolidação
informa o estado atual, sem apagar os resultados e limites anteriores.

| Entrega | Estado confirmado | Conferência que permanece |
| --- | --- | --- |
| #1–#6, #16 e #22 | Base funcional, piloto técnico e Release v1.0.0 concluídos | Acompanhamento de backups e ensaios periódicos; limites de avaliação sintética preservados |
| #23 / PR #29 | Página pública implantada; Manex confirmou atualização do Google Branding, flags, links e apresentação em PC/celular | Não equivale a auditoria de acessibilidade ou aceite de verificação pelo Google |
| #24 / PR #31 | Implementação integrada e aceite local geral confirmado; código incluído na implantação posterior | Roteiro específico de tela estreita/celular, zoom e teclado/foco em /app/ sem confirmação individual |
| #32 / PR #33 | Aceite visual local da home e dos índices Organização/Planejamento; validação em produção confirmada | Não há confirmação individual de todas as larguras, zoom, teclado, temas e estados do roteiro |
| #25 / PR #34 | Implementação integrada e aceite local confirmado; código incluído na implantação posterior | Matriz completa de estados vazios por perfil em produção não confirmada explicitamente |
| #35/#36 / PRs #37/#38 | Integração, aceite local, implantação, ativação de turnos e roteiro final de produção aprovados por Manex em 21/11 | Sem novo ensaio de restauração pós-ativação nesta rodada; regra entre setores em #39 |

## Evidências consolidadas de turnos

- Migrações aplicadas e perfis sincronizados; conferência de migrações sem pendências e check sem problemas, informados pelo operador.
- Ativação e configuração de responsáveis, vínculos e equipe confirmadas.
- Manex confirmou aprovação do roteiro final: isolamento de setores/turnos, acesso direto,
  bloqueio de conclusão compartilhada, visão do Coordenador, cadastro com/sem turno,
  troca revisada com histórico/preservação do passado, estilos e seletores.
- Verificação de saúde e backup posterior à ativação concluídos com sucesso, conforme os resultados apresentados.
- CI do conteúdo final da PR #38: 223 testes Django em PostgreSQL 17, quatro de backup,
  build e smoke aprovados. [Execução](https://github.com/AldomarAssolin/op-app-industrial/actions/runs/44958089772).
- Discussões de revisão das PRs #37/#38 resolvidas. A revisão automática original não
  foi repetida sobre todos os commits posteriores; CI e aceite não são uma nova revisão Codex.

O padrão False da opção de turnos para novas instalações é mantido. Não confundir padrão
de configuração com o estado do ambiente ativado pelo operador.

## Próxima sequência

1. [#39 — regra entre setores](https://github.com/AldomarAssolin/op-app-industrial/issues/39):
   definir proibição ou cessão autorizada e comportamento por perfil antes ou durante o refinamento da #26.
   Nenhuma regra, alocação ou histórico foi alterado nesta reconciliação.
2. #26: fluxo de planejamento com seleção, revisão e confirmação.
3. #27: integração do quadro semanal, retorno ao contexto e filtros.
4. #28: avaliação de uso com participante e consolidação da próxima versão proposta v1.1.0.

As #26/#27/#28 são próximas entregas, não implementações antigas esquecidas. A tag v1.0.0
preserva o MVP inicial e não inclui as evoluções posteriores da main; não será movida.
Escalas, cálculo de horas e retificação de eventos de turno já confirmados permanecem
fora do escopo documentado. Uso de dados reais continua sujeito à autorização e às
responsabilidades operacionais previamente definidas.

Esta reconciliação altera somente documentação e registros de planejamento/aceite.
