# Planejamento operacional e quadro — #26/#27

## Fluxo

`/planejamento/planejar/` oferece tarefa, pessoas, função, turno (quando habilitado),
período e dias da semana. Até 1.000 alocações por confirmação. As opções usam o escopo
atual e o habitual no início informado; ao mudar o início, o seletor atualiza as opções.
Todos os dias escolhidos são revalidados individualmente no backend.

Revisar não grava. A tela identifica tarefa, setor, função, turno, pessoas, datas e quantidade.
A confirmação assinada expira em 30 minutos, pertence ao usuário e à configuração de turnos.
O POST final recarrega e revalida acesso, participação da tarefa, atividade, datas, habitual,
conflitos e duplicidade. Mudanças nos dados revisados exigem nova revisão. Erros preservam
escolhas quando ainda autorizadas, sem mostrar nomes fora do escopo.

A confirmação trava ator, tarefa e trabalhadores em ordem global. Inclusão de alocações,
histórico e recibo ocorre na mesma transação. Recibo durável por UUID torna o reenvio do
mesmo token idempotente, inclusive com concorrência e turnos desabilitados. Outra revisão
com o mesmo conteúdo é outra operação e continua sujeita à regra de duplicidade exata.
Se os dados forem corrigidos/removidos depois, reenviar um recibo não recria alocações.
Não há inferência de horas, jornada exclusiva, capacidade ou disponibilidade.

A navegação principal leva ao novo fluxo; Admin permanece para tarefas, equipe e apoio.
O fluxo operacional exige login e permissões de operação/escopo; não depende de staff,
que continua necessário para acessar destinos do Admin. Consulta não grava, mesmo com
permissão individual incompatível. Flags e grupos não são alterados por estas telas.

## Quadro, filtros e correção

O quadro abre na semana atual e aceita setor, turno, trabalhador, tarefa, dia e status.
O dia é relativo à semana consultada: ao avançar uma semana, Segunda continua Segunda.
Por decisão de Manex, mostra somente a coluna escolhida, inclusive sábado ou domingo.
Limpar filtros mantém a semana. Seleção, navegação, planejamento, correção e impressão
preservam contexto validado; não há redirecionamento para URL externa fornecida pelo cliente.

Opções/resultados são autorizados no backend. Trabalhadores de alocações históricas
visíveis continuam disponíveis no filtro, mesmo se o habitual mudou. Legado sem turno só
aparece a quem já pode consultá-lo. Status é explicitamente o estado **atual** da tarefa,
inclusive em semanas passadas; não reconstitui o estado histórico naquela semana.

O quadro diferencia semana vazia, combinação sem resultados e ausência de acesso sem
revelar registros ocultos. Correção/remoção aparecem conforme permissões, com endpoints
independentes igualmente protegidos. A correção permite trabalhador autorizado, data,
função e observação; tarefa e turno daquele registro permanecem identificados. Troca de
habitual e transferência futura continuam no fluxo do Coordenador da #35/#36.

Salvar correção exige versão assinada do registro, revalidada sob os bloqueios; edição
concorrente rejeita sobrescrita. Remoção exige confirmação por POST/CSRF; só remove aquele
dia e preserva o histórico de turno. Ambas retornam à mesma semana/filtros, quando ainda
autorizados. Não há gravação por GET nem alteração das regras de acesso da #35/#36.

## Migração e limites

`planejamento.0006_confirmacaoplanejamento` acrescenta recibos sem modificar alocações
existentes. Aplicar `migrate` antes de iniciar a nova versão. Reversão recusa apagar recibos
já usados; recuperar imagem/banco compatíveis em ensaio isolado quando necessário.

Manex decidiu manter a regra entre setores atual: #39 adiada para outra versão. Não foi
implementado empréstimo de equipe nem proibição nova, inclusive para perfis globais.
A avaliação com participante e a verificação aprofundada de dispositivo, acessibilidade,
filtros e concorrência continuam na #28; testes automatizados não substituem esse aceite.
