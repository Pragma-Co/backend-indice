# Estrutura de projeto — Backend Django

Este documento descreve a organização recomendada para o backend em Django, com foco em clareza, manutenção e legibilidade para desenvolvedores e para uso por inteligências artificiais.

## 1) Visão geral

Para um projeto pequeno ou de médio porte, a estrutura mais clara é manter o projeto Django principal em `api6/` e organizar o app principal em camadas: `models/`, `views/`, `services/`, `serializers/`, `tests/`, `migrations/` e `urls.py`.

Essa organização ajuda a separar:

- regras de persistência
- regras de negócio
- endpoints da API
- serialização de dados
- testes
- integração com o banco de dados

---

## 2) Estrutura recomendada para este projeto

```text
backend-api-6/
├── .env
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── LICENSE
├── manage.py
├── README.md
├── requirements.txt
├── PROJECT_STRUCTURE.md
├── scripts/
│   └── setup_env.py
├── api6/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── urls.py
│   ├── mongo.py
│   ├── migrations/
│   │   └── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── health.py
│   ├── views/
│   │   ├── __init__.py
│   │   └── health_view.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── health_service.py
│   ├── serializers/
│   │   ├── __init__.py
│   │   └── health_serializer.py
│   └── tests/
│       ├── __init__.py
│       └── test_health.py
└── .dockerignore
```

### Significado das pastas principais

- `api6/`: projeto Django principal
  - `settings.py`: configurações gerais do projeto
  - `urls.py`: roteamento principal do projeto
  - `asgi.py` e `wsgi.py`: ponto de entrada do servidor

- `core/`: app principal do backend
  - `models/`: modelos de domínio e dados
  - `views/`: módulos de visualização/endpoint
  - `services/`: regras de negócio e lógica de aplicação
  - `serializers/`: conversão entre modelos e JSON
  - `tests/`: testes do app
  - `migrations/`: histórico de banco
  - `mongo.py`: integração com MongoDB
  - `urls.py`: rotas do app

- `scripts/`: automações e utilitários de setup do ambiente

- `.env` e `.env.example`: configurações sensíveis do projeto

---

## 3) Organização por responsabilidade

Cada parte do app deve ter uma função clara:

- `models/`: entidades e estrutura de dados
- `services/`: regra de negócio, validações e lógica que não fica no modelo
- `views/`: endpoints HTTP e resposta ao cliente
- `serializers/`: transformação de objeto para JSON e vice-versa
- `tests/`: testes unitários e de integração
- `migrations/`: histórico de alterações do banco
- `urls.py`: registro das rotas do app

Regra geral:

- modelos não devem conter toda a lógica de negócio
- views não devem executar regras complexas diretamente
- services devem concentrar a lógica de aplicação
- serializers devem cuidar apenas da serialização e validação de entrada/saída

---

## 4) Convenções de nomenclatura

Para manter o backend legível e útil para IA, siga estas regras:

- usar `snake_case` para arquivos e pastas Python
- usar nomes claros e específicos, como `health_service.py`, `user_serializer.py`
- evitar nomes genéricos como `utils.py` espalhados sem contexto
- manter uma responsabilidade por arquivo
- manter `urls.py`, `models/`, `views/`, `services/`, `serializers/` e `tests/` bem definidos

---

## 5) Regras para IA e manutenção

Este projeto deve ser organizado de forma que uma IA ou um novo desenvolvedor consiga responder rapidamente:

1. onde ficam as configurações do projeto
2. onde ficam os endpoints
3. onde ficam os modelos e regras de negócio
4. onde ficam os testes
5. onde ficam os scripts de ambiente e deploy

Para isso, recomenda-se:

- manter documentação clara em `README.md` e `PROJECT_STRUCTURE.md`
- usar nomes que expressem a função do arquivo
- preservar uma hierarquia lógica entre infraestrutura, domínio e testes
- manter o app principal organizado por camada e não misturar responsabilidades

---

## 6) Diretriz final

Para este backend, a estrutura mais adequada é a organização em camadas dentro do app principal: `models/`, `views/`, `services/`, `serializers/`, `tests/` e `migrations/`.

Essa abordagem mantém o projeto simples, previsível e fácil de entender tanto para humanos quanto para ferramentas de inteligência artificial.
