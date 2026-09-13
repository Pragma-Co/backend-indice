/**
 * Convencao de commit do projeto.
 *
 * Fonte da verdade: documentation/process/Commit Standards.md, no repositorio
 * pai. Mudou aqui, atualize la tambem — e vice-versa.
 *
 *   tipo(escopo): descricao em ingles, sem ponto final
 *
 * O escopo e o numero do card (#12) ou, quando nao existe card, o
 * identificador do requisito (FR1, NFR2). Quando a mudanca tem card e
 * requisito, use sempre o card.
 *
 * Exemplos validos:
 *   feat(#12): implement document search filters
 *   fix(#18): prevent unauthorized document access
 *   devops(#30): update CI/CD workflow
 *   docs(FR2): update document processing documentation
 *   chore: bump dependency versions
 */

const TIPOS = [
  'chore',
  'devops',
  'docs',
  'feat',
  'fix',
  'refactor',
  'style',
  'test',
];

// Tipos de manutencao que podem vir sem escopo, como ja acontece no historico
// do projeto. Para todos os outros o escopo e obrigatorio.
const TIPOS_SEM_ESCOPO = new Set(['chore', 'docs']);

// Numero do card (#12) ou identificador de requisito (FR1, NFR2).
const ESCOPO = /^(#\d+|N?FR\d+)$/;

const HEADER =
  /^(?<tipo>[A-Za-z]+)(?:\((?<escopo>[^()]*)\))?(?<breaking>!)?: (?<descricao>.+)$/;

const EXEMPLO = 'feat(#12): implement document search filters';

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
              `formato invalido. Use "tipo(escopo): descricao" — ex.: ${EXEMPLO}`,
            ];
          }

          const { tipo, escopo } = match.groups;

          if (!TIPOS.includes(tipo)) {
            return [
              false,
              `tipo "${tipo}" invalido. Use um de: ${TIPOS.join(', ')}`,
            ];
          }

          if (escopo !== undefined && !ESCOPO.test(escopo)) {
            return [
              false,
              `escopo "(${escopo})" invalido. Use o numero do card (#12) ou o requisito (FR1, NFR2) — ex.: ${EXEMPLO}`,
            ];
          }

          if (escopo === undefined && !TIPOS_SEM_ESCOPO.has(tipo)) {
            return [
              false,
              `o tipo "${tipo}" exige escopo — ex.: ${tipo}(#123): descricao`,
            ];
          }

          return [true];
        },
      },
    },
  ],
};
