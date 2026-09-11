# CLAUDE.md

Guidance for AI assistants (Claude Code) and new developers working on this repository.
The team standards live in the `indice` documentation repository; this file condenses the
parts that apply day to day. When in doubt, the team documentation wins.

## Project

Django 5.2 backend of the "Índice" document management system (FATEC API-6, Pragma-Co).
PostgreSQL through the Django ORM, MongoDB through `pymongo` (`core/mongo.py`). Plain
`JsonResponse` views, no Django REST Framework. Everything runs in Docker; see `README.md`
for setup, ports and useful commands.

The Vue frontend (separate repository) calls the API through a Vite proxy that strips the
`/api` prefix, so routes live at the project root next to `/health/`.

## Language

All code is written in English: module, class, function, variable and field names, docstrings,
comments, log and validation messages, admin labels, URL paths, JSON keys and test names.
Only client-defined domain data (seed values such as `Estruturas`, `Memorial de Cálculo`) and
user-facing texts agreed with the client stay in Portuguese.

## Repository structure

The `core` app is organized by layer (`PROJECT_STRUCTURE.md` standard):

```
core/
├── models/        # entities grouped by subject (catalog, document, revision, ...), exported from __init__.py
├── views/         # HTTP endpoints, <resource>_view.py
├── services/      # business rules, <topic>_service.py
├── serializers/   # model <-> JSON, <topic>_serializer.py
├── tests/         # test_<topic>.py
├── migrations/    # 0001 creates the schema, 0002 adds database triggers
├── management/    # commands (ensure_superuser, seed)
├── admin.py
└── mongo.py
```

- Routes are registered in `api6/urls.py`, importing views directly from their modules.
- Models hold data and database constraints, not business rules.
- Views never run complex logic; they call services and return responses.
- Services concentrate application logic. Serializers only convert.
- `snake_case`, one responsibility per file, specific names, no generic `utils.py`.
- The user model is `core.User` (login by email, role-based admin access). Every user
  belongs to an `Area`.

## Git workflow (Gitflow)

- Never commit on `main`. Create work branches from `develop`.
- Branch name: `<type>/<card-id>-short-english-description`, e.g. `feat/12-document-search`,
  `fix/18-document-access-validation`, `docs/21-update-installation-guide`. Use the commit
  type as prefix (`feat/`, not `feature/`). The description follows the card title.
- Also `release/*` (from `develop`) and `hotfix/*` (from `main`, merged back into both).
- When a branch depends on another unmerged branch, rebase on top of it and open the PR
  with that branch as base; never re-commit someone else's work as your own.
- Do not push or open pull requests unless explicitly asked. Never force-push without approval.

## Commits (Conventional Commits)

Format: `<type>(#<card-id>): <short message in English>`, imperative mood. When no card
exists, use the requirement id instead: `docs(RF1): document multidimensional search`.
If both exist, the card id wins.

| Type | Use |
|------|-----|
| feat | New functionality |
| fix | Bug fixes |
| docs | Documentation |
| style | Formatting only |
| refactor | Code change without functional change (e.g. reorganizing modules) |
| test | Adding or changing tests |
| chore | Auxiliary tasks, dependencies, configuration |
| devops | CI/CD, automation, infrastructure |

One logical change per commit. No generic messages (`update`, `changes`, `fix`).

Commits and pull requests are authored solely by the developer's git identity. Do not add
`Co-Authored-By`, "Generated with" or any other AI attribution to commit messages or PRs.

## Tests

- Plain Django `TestCase`/`SimpleTestCase`, run inside the container:
  `docker compose exec api python manage.py test`.
- Behavior-driven structure with explicit comments in every test:

```python
def test_should_return_disciplines_ordered_by_name(self):
    # Given
    ...
    # When
    ...
    # Then
    ...
```

- Mandatory coverage: business rules (services), model methods and validations, API endpoints
  (views), validations, permissions and access control, document processing, error handling.
  Not required: environment and infrastructure configuration, trivial migrations.
- Prefer behavior over implementation details; keep tests reproducible; fix broken tests before
  integrating. The default test client skips CSRF, so use `Client(enforce_csrf_checks=True)`
  when asserting real HTTP method rejection.

## Error handling and LGPD

- HTTP responses never expose hosts, usernames, SQL or stack traces. Log the full exception
  server-side and answer `{"error": "<ExceptionName>"}` (see `core/views/health_view.py`).
- Never commit `.env` or `CREDENTIALS.txt`; never log or seed real personal data.

## Environment rules

- Do not change ports, `.env` values, `docker-compose.yml` or other configuration on your
  own. If a port is taken by another local service, stop that service instead.
- Do not delete database volumes (`docker compose down -v`) without explicit approval.

## Pull requests, review and CI

- Every change reaches `develop` through a PR with a clear description tied to the card or
  requirement, reviewed by at least one teammate and merged only after CI passes.
- CI runs only on PRs targeting `develop`, `main` or `release/*`; pushes to work branches do
  not trigger it.
- Review checklist: acceptance criteria met, code works, tests implemented and passing, CI
  green, business rules respected, clear naming, no needless duplication, proper error
  handling, security considered, documentation updated, commits in the standard format.
- Definition of Ready / Definition of Done:
  https://github.com/Pragma-Co/indice/tree/main/documentation/DoR%20%26%20DoD
