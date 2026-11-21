# Aceite do MVP — 21/11/2026

## Produto entregue

OP-APP apoia o planejamento operacional industrial com cadastros de setores, funções
e trabalhadores, tarefas com histórico, alocações diárias e consulta semanal.
Uma pessoa pode participar de tarefas diferentes no mesmo dia; alocação não contabiliza
horas nem comprova capacidade disponível.

## Aceite e evidências

Manex confirmou os roteiros locais e os testes acompanhados do piloto. A execução
agendada da cópia de segurança foi confirmada nesta data. Foram concluídos também os
ensaios de recuperação do banco e da aplicação com conteúdo sintético, com validação
dos dados e do funcionamento HTTP. A configuração necessária à recuperação foi
testada fora do ambiente hospedado.

Esses resultados foram executados e informados pelo operador. O assistente não teve
acesso independente ao servidor. Detalhes operacionais permanecem no registro privado
do acompanhamento; este documento não publica configuração de infraestrutura.

A implementação base da versão é a main anterior à evolução da página pública,
commit `671ea7f61f7f8e5811ea44dd4b3fb83e6006e14a`. Sua comparação com o head
aprovado da PR #21 não apresenta diferenças de arquivos. O CI dessa entrega aprovou
126 testes Django e quatro testes separados da rotina de backup:
[execução](https://github.com/AldomarAssolin/op-app-industrial/actions/runs/44770433848).

## Limites da versão

- Avaliação controlada com dados sintéticos; autorização para dados reais é uma
  decisão específica, não concedida pela tag ou Release.
- Ensaio realizado na infraestrutura existente, sem reconstrução completa do servidor.
- Interface inicial baseada em Django Admin e Templates; sem isolamento entre empresas,
  contratação autônoma, cobrança, controle de horas ou apontamento de produtividade.
- Manutenção, acompanhamento das cópias e ensaios periódicos continuam necessários
  depois do encerramento desta entrega.

Os roteiros em docs/ descrevem procedimentos e, quando históricos, registram pendências
da data original. Para o estado consolidado do aceite inicial, usar este documento e
as issues #16 e #22; não tratar instruções de instalação como execução ainda pendente.

## Próxima evolução

A PR #29 e as issues #23–#28 tratam da apresentação e experiência operacional.
Não integram o código da primeira versão. A Release deve identificar um commit conhecido,
preservando esse marco antes de incorporar as melhorias.
