# OP-APP v1.1.0-rc.1 — candidata à validação

## Entregas

- Planejamento com seleção de múltiplos trabalhadores/dias, revisão e confirmação atômica.
- Reenvio de confirmação sem duplicar alocações, com recibo persistente.
- Filtros combinados do quadro: setor, turno, trabalhador, tarefa, dia e status atual.
- Filtro de dia em coluna única; contexto preservado ao navegar, planejar e corrigir.
- Correção e remoção de um registro pelo quadro, com permissão, CSRF e controle de edição concorrente.
- Evoluções anteriores da main: apresentação pública, entrada, orientação, Admin e turnos.

## Estado

Notas preparadas para a candidata; esta página não afirma publicação da tag/Release,
implantação ou execução de teste manual. A v1.0.0 permanece imutável como marco inicial.
As #26/#27 completam o escopo de código; #28 continua como avaliação mais aprofundada após
a candidata. Sem alegação de avaliação externa, ganho de produtividade ou uso empresarial.
A regra entre setores (#39) foi explicitamente adiada por Manex e permanece inalterada.

## Atualização e aceite básico

1. Backup verificado antes de atualizar qualquer ambiente com dados.
2. Aplicar migrações (`python manage.py migrate --noinput`) antes do uso da nova versão.
3. Conferir `python manage.py migrate --check` e `python manage.py check`.
4. Como Líder, planejar duas pessoas do mesmo turno por quatro dias, revisar e confirmar;
   reenviar a confirmação e conferir que não duplicou. Tarefa extra no mesmo turno/dia é permitida.
5. Combinar filtros; escolher um dia e navegar entre semanas; planejar e voltar ao contexto.
6. Corrigir/remover um dia e conferir os demais. Consulta não recebe escrita. Conferir
   URLs e opções fora do setor/turno e preservar dados na rejeição.
7. Conferir desktop, celular e impressão. Registrar evidência e dificuldades na #28.

Nova tabela: ConfirmacaoPlanejamento. Não há variável de ambiente nova. Não desabilitar
turnos como estratégia de reversão após uso; isso restaura a política anterior por setor.
Leia [planejamento-operacional.md](planejamento-operacional.md) e [autorizacao-turnos.md](autorizacao-turnos.md).
