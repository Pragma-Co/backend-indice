/**
 * Convencao de commit do projeto:
 *
 *   tipo(#issue): descricao em minusculo, sem ponto final
 *
 * Exemplos validos:
 *   feat(#50): adiciona endpoint de upload de documentos
 *   fix(#9): corrige texto do botao de cancelar
 *   chore: atualiza porta padrao do banco
 *
 * O numero da issue e obrigatorio, exceto para os tipos de manutencao
 * listados em TIPOS_SEM_ISSUE.
 */

const TIPOS = [
  'build',
  'chore',
  'ci',
  'docs',
  'feat',
  'fix',
  'perf',
  'refactor',
  'revert',
  'style',
  'test',
];

const TIPOS_SEM_ISSUE = new Set(['build', 'chore', 'ci', 'docs', 'revert']);

const HEADER = /^(?<tipo>[A-Za-z]+)(?:\((?<escopo>[^()]*)\))?(?<breaking>!)?: (?<descricao>.+)$/;

const EXEMPLO = 'feat(#50): adiciona endpoint de upload';

export default {
  // O parser padrao do commitlint nao aceita "#" no escopo, entao usamos o nosso.
  parserPreset: {
    parserOpts: {
      headerPattern: /^(\w+)(?:\(([^()]*)\))?!?: (.+)$/,
      headerCorrespondence: ['type', 'scope', 'subject'],
    },
  },

  rules: {
    'header-max-length': [2, 'always', 120],
    'subject-full-stop': [2, 'never', '.'],
    'convencao-commit': [2, 'always'],
  },

  plugins: [
    {
      rules: {
        'convencao-commit': ({ header }) => {
          const match = HEADER.exec(header);

          if (!match) {
            return [
              false,
              `formato invalido. Use "tipo(#issue): descricao" — ex.: ${EXEMPLO}`,
            ];
          }

          const { tipo, escopo } = match.groups;

          if (!TIPOS.includes(tipo)) {
            return [
              false,
              `tipo "${tipo}" invalido. Use um de: ${TIPOS.join(', ')}`,
            ];
          }

          if (escopo !== undefined && !/^#\d+$/.test(escopo)) {
            return [
              false,
              `escopo "(${escopo})" invalido. O escopo deve ser o numero da issue — ex.: ${EXEMPLO}`,
            ];
          }

          if (escopo === undefined && !TIPOS_SEM_ISSUE.has(tipo)) {
            return [
              false,
              `o tipo "${tipo}" exige o numero da issue — ex.: ${tipo}(#123): descricao`,
            ];
          }

          return [true];
        },
      },
    },
  ],
};
