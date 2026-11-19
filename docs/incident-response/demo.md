# Roteiro de demonstração: incidentes de dados pessoais

Cerca de 15 minutos, na ordem em que um incidente real acontece. Executado de ponta a ponta no ambiente local em 17/11/2026. O plano que este roteiro demonstra está em [plan.md](plan.md).

## Preparo

- `docker compose up -d`, `docker compose exec api python manage.py migrate` e `seed`. A senha dos usuários do seed é a `SEED_PASSWORD` usada ao semear.
- Os comandos de backup e de reaplicação precisam de `BACKUP_ENCRYPTION_KEY` (64 caracteres hexadecimais) no `.env`. Sem ela, passe a chave no próprio comando: `docker compose exec -e BACKUP_ENCRYPTION_KEY=<chave> api python manage.py ...`.
- Os passos 5 e 10 dependem do código dos PRs #70 (SCRUM-102) e #66 (SCRUM-101) no branch em uso.
- Não há tela no frontend, então a demonstração usa a API direto (curl, Insomnia ou Postman), o admin do Django em `http://127.0.0.1:8000/admin/` e o Mailpit em `http://127.0.0.1:8025` para os e-mails.

## 1. Entrar como administradora e aceitar os termos

O cookie de CSRF vem primeiro, depois o login. O token de CSRF muda depois do login, por isso ele é relido antes das outras chamadas. O arquivo `cookies.txt` guarda a sessão.

```bash
BASE=http://127.0.0.1:8000
curl -s -c cookies.txt "$BASE/auth/csrf"
CSRF=$(grep csrftoken cookies.txt | awk '{print $7}')
curl -s -b cookies.txt -c cookies.txt -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" \
  -X POST "$BASE/auth/login" -d '{"email": "marina.duarte@akaer.local", "password": "<SEED_PASSWORD>"}'
CSRF=$(grep csrftoken cookies.txt | awk '{print $7}')
api() { curl -s -b cookies.txt -c cookies.txt -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" "$@"; }
```

Quem tem termos de uso publicados sem aceite recebe `403 {"error": "LegalAcceptanceRequired"}` em todas as rotas. No seed a administradora ainda não aceitou: o primeiro comando lista os termos pendentes (a versão fica em `results[].current_version`, com `id` e `clauses[].id`); o segundo monta o aceite de todas as cláusulas e envia.

```bash
api "$BASE/users/me/legal-pending"
api -X POST "$BASE/users/me/legal-acceptances" -d "$(api "$BASE/users/me/legal-pending" | python3 -c "
import sys, json
v = json.load(sys.stdin)['results'][0]['current_version']
print(json.dumps({'version_id': v['id'], 'consents': [{'clause_id': c['id'], 'accepted': True} for c in v['clauses']]}))")"
```

Para mostrar o bloqueio dos outros perfis, repita o login em outro arquivo de cookies com `thiago.serpa@akaer.local` (auditor) e chame `GET /security/incidents`: a resposta é `403 {"error": "PermissionDenied"}`.

## 2. Registrar o incidente

Os ids de usuários e documentos afetados vêm de `GET /users` e `GET /documents`.

```bash
api -X POST "$BASE/security/incidents" -d '{
  "title": "Planilha enviada ao fornecedor errado",
  "description": "Planilha com nome, e-mail e cargo de 12 colaboradores anexada ao e-mail errado",
  "incident_type": "MISDIRECTED_DELIVERY",
  "severity": "HIGH",
  "occurred_at": "2026-11-16T14:00:00-03:00",
  "detected_at": "2026-11-17T09:30:00-03:00",
  "affected_data_categories": ["IDENTIFICATION", "PROFESSIONAL"],
  "affected_subjects_count": 12,
  "affected_user_ids": [3, 13],
  "affected_document_ids": [<id de um documento de GET /documents>]
}'
```

A resposta `201` traz a referência (`INC-2026-0001`), o status `REPORTED` e, em `authority_notification`, o prazo `due_at` três dias úteis depois da detecção. Guarde o `id` para as chamadas seguintes (abaixo, `1`).

## 3. Registrar a ação de contenção e avançar de etapa

```bash
api -X POST "$BASE/security/incidents/1/actions" -d '{"kind": "CONTAINMENT", "description": "Pedido de exclusão do e-mail ao fornecedor, confirmado por telefone"}'
api -X POST "$BASE/security/incidents/1/status" -d '{"status": "CONTAINMENT", "note": "Fornecedor confirmou a exclusão"}'
api -X POST "$BASE/security/incidents/1/status" -d '{"status": "ANALYSIS"}'
api -X PATCH "$BASE/security/incidents/1" -d '{"root_cause": "Autocompletar do cliente de e-mail"}'
api -X POST "$BASE/security/incidents/1/status" -d '{"status": "RESOLVED"}'
```

## 4. Tentar encerrar antes das comunicações

```bash
api -X POST "$BASE/security/incidents/1/status" -d '{"status": "CLOSED"}'
```

A resposta é `409 {"error": "IncidentClosureBlocked", "reasons": ["authority_not_notified", "data_subjects_not_notified"]}`.

## 5. Comunicar os titulares pelo sistema

O `GET` mostra quem será avisado (os usuários listados no incidente) e a prévia exata do e-mail; o `POST` envia e devolve o resultado.

```bash
api "$BASE/security/incidents/1/subject-notifications"
api -X POST "$BASE/security/incidents/1/subject-notifications"
```

No `GET`, mostre `recipients` (os usuários listados em `affected_user_ids`, com status `PENDING`) e `preview.text`. No `POST`, `result` traz `sent`, `failed` e `skipped`, cada destinatário passa a `SENT` com `sent_at`, e o incidente ganha `subjects_notified_at`. Em desenvolvimento as mensagens chegam ao Mailpit, o container que captura os e-mails: abra `http://127.0.0.1:8025` e mostre a mensagem com o texto e a versão HTML. (Se `EMAIL_BACKEND` estiver no backend de console, elas aparecem no log da api: `docker compose logs api --since 5m | grep -A 40 "Comunicado sobre incidente"`.)

Um segundo `POST` não reenvia a ninguém (`skipped`). Para mostrar falha e reenvio, aponte `EMAIL_BACKEND` para SMTP com um `EMAIL_HOST` inalcançável, reinicie a api e envie: os destinatários ficam `FAILED` com `last_error`; a rotina do servidor reenvia só esses, até três tentativas:

```bash
docker compose exec api python manage.py send_incident_notifications
```

## 6. Registrar a comunicação à ANPD

Ela acontece fora do sistema; o administrador registra a data (sem `notified_at`, vale o momento da chamada).

```bash
api -X POST "$BASE/security/incidents/1/notifications" -d '{"recipient": "AUTHORITY"}'
```

O detalhe do incidente passa a mostrar `authority_notification.notified_at` e `overdue: false`. A lista `GET /security/incidents?overdue=true` mostra os que estouraram o prazo sem registro.

## 7. Encerrar

```bash
api -X POST "$BASE/security/incidents/1/status" -d '{"status": "CLOSED"}'
api -X POST "$BASE/security/incidents/1/actions" -d '{"kind": "OTHER", "description": "tarde demais"}'
api "$BASE/security/incidents/1"
```

O primeiro comando responde `200` com `closed_at`; o segundo, `409 {"error": "IncidentClosed"}`. O `GET` do detalhe mostra `actions` e `status_changes` com autor e data: é o histórico que o banco não deixa editar.

## 8. Admin do Django

Em `http://127.0.0.1:8000/admin/`, com o mesmo e-mail e senha: "Data incidents" mostra o incidente com ações e histórico somente leitura; "Audit log" mostra a trilha com `INCIDENT_REGISTERED`, `INCIDENT_STATUS_CHANGED`, `INCIDENT_SUBJECTS_NOTIFIED`; "Backup runs" mostra os snapshots do passo 9.

## 9. Gerar, consultar e abrir um snapshot

```bash
docker compose exec api python manage.py backup_snapshot                    # os dois bancos
docker compose exec api python manage.py backup_snapshot --target postgres  # só um
ls -la backups/postgres backups/mongodb
```

Cada execução imprime `POSTGRES: SUCCEEDED <arquivo>` e entra no histórico, que o administrador consulta pela API:

```bash
api "$BASE/security/backups"
```

Para provar que o arquivo é ilegível sem a chave e legível com ela:

```bash
head -c 48 backups/postgres/<arquivo>.json.gz.enc | xxd                     # bytes cifrados
docker compose exec api python manage.py backup_decrypt backups/postgres/<arquivo>.json.gz.enc
head -c 400 backups/postgres/<arquivo>.json                                # JSON em claro
docker compose exec -e BACKUP_ENCRYPTION_KEY=$(openssl rand -hex 32) api python manage.py backup_decrypt backups/postgres/<arquivo>.json.gz.enc   # chave errada: falha com InvalidTag
```

Apague o `.json` em claro depois da demonstração: ele contém dados pessoais. O agendamento é o crontab do servidor, com as duas linhas do README (PostgreSQL `0 */4 * * *`, MongoDB `0 3 * * *`).

## 10. Reaplicar uma exclusão depois de um restore

Use um usuário descartável: a exclusão é definitiva e o e-mail fica bloqueado para novos cadastros, inclusive para o `seed`. Simule o retorno da pessoa em quatro passos: ela pede a exclusão, o registro vai para um snapshot, a linha dela é colocada de volta como um restore faria, e o comando reaplica.

```bash
# 0. usuário descartável (anote o id impresso)
docker compose exec api python manage.py shell -c "
from core.models import Area, Role, User
u = User.objects.create_user(email='demo.titular@akaer.local', password='<senha>', name='Demo Titular', role=Role.VIEWER, area=Area.objects.get(acronym='MFG'))
print(u.pk)"

# 1. a pessoa pede a exclusão da conta (sessão dela, não a do admin; token relido depois do login)
curl -s -c u.txt "$BASE/auth/csrf"; U=$(grep csrftoken u.txt | awk '{print $7}')
curl -s -b u.txt -c u.txt -H "X-CSRFToken: $U" -H "Content-Type: application/json" -X POST "$BASE/auth/login" -d '{"email": "demo.titular@akaer.local", "password": "<senha>"}'
U=$(grep csrftoken u.txt | awk '{print $7}')
curl -s -b u.txt -c u.txt -H "X-CSRFToken: $U" -X POST "$BASE/users/me/request-deletion"

# 2. snapshot com o registro de exclusões atualizado
docker compose exec api python manage.py backup_snapshot --target postgres

# 3. "restauro" a linha da pessoa como estava antes (o que um loaddata antigo faria)
docker compose exec api python manage.py shell -c "
from core.models import User
User.objects.filter(pk=<id>).update(email='demo.titular@akaer.local', name='Demo Titular', is_active=True)"

# 4. a reaplicação encontra a pessoa no registro e a anonimiza de novo
docker compose exec api python manage.py reapply_user_erasures --from-snapshot backups/postgres/<arquivo do passo 2>.json.gz.enc
```

O passo 1 responde `{"message": "Account deactivated and anonymized."}` e o passo 4 imprime `Register entries merged from the snapshot: N` e `Anonymized 1, deleted 0, failed 0.`. Mostre o antes e o depois no admin do Django: o usuário volta a `Usuário removido`, inativo, e a trilha de auditoria ganha `USER_ERASURE_REAPPLIED` com `kind: ANONYMIZED`.

## Restauração real

Em um banco vazio (ou num ambiente de teste), depois de descriptografar o snapshot:

```bash
docker compose exec api python manage.py migrate
docker compose exec api python manage.py loaddata backups/postgres/<arquivo>.json
docker compose exec api python manage.py reapply_user_erasures --from-snapshot backups/postgres/<arquivo mais recente>.json.gz.enc
```

Com `failed` maior que zero, o comando termina com erro listando os usuários sem gestor substituto, para tratamento manual.
