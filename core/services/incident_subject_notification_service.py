import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import (
    DataIncident,
    DataIncidentSubjectNotification,
    DocumentAccess,
    Revision,
)
from core.models.choices import (
    IncidentActionKind,
    IncidentStatus,
    IncidentType,
    PersonalDataCategory,
    SubjectNotificationReason,
    SubjectNotificationStatus,
)
from core.services.data_incident_exceptions import (
    IncidentClosedError,
    IncidentNotFoundError,
    NoAffectedUsersError,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
SUBJECT_PREFIX = "[Índice] Comunicado sobre incidente de segurança"
TEXT_TEMPLATE = "emails/data_incident_subject_notification.txt"
HTML_TEMPLATE = "emails/data_incident_subject_notification.html"
MEASURE_KINDS = (
    IncidentActionKind.CONTAINMENT,
    IncidentActionKind.ERADICATION,
    IncidentActionKind.RECOVERY,
)

INCIDENT_TYPE_LABELS = {
    IncidentType.UNAUTHORIZED_ACCESS: "acesso não autorizado",
    IncidentType.IMPROPER_DISCLOSURE: "divulgação indevida",
    IncidentType.DATA_LOSS: "perda ou destruição de dados",
    IncidentType.CREDENTIAL_EXPOSURE: "exposição de credenciais",
    IncidentType.MISDIRECTED_DELIVERY: "envio a destinatário incorreto",
    IncidentType.MALICIOUS_SOFTWARE: "software malicioso",
    IncidentType.OTHER: "outro",
}

DATA_CATEGORY_LABELS = {
    PersonalDataCategory.IDENTIFICATION: "dados de identificação (nome, e-mail)",
    PersonalDataCategory.CREDENTIALS: "credenciais de acesso",
    PersonalDataCategory.PROFESSIONAL: "dados profissionais (cargo, área)",
    PersonalDataCategory.ACCESS_HISTORY: "histórico de acessos e auditoria",
    PersonalDataCategory.DOCUMENT_CONTENT: "conteúdo de documentos técnicos",
    PersonalDataCategory.OTHER: "outros dados pessoais",
}

DATA_CATEGORY_GUIDANCE = {
    PersonalDataCategory.IDENTIFICATION: (
        "Desconfie de e-mails, mensagens ou ligações que citem seus dados ou peçam informações "
        "adicionais; a equipe do Índice nunca solicita senhas por esses canais."
    ),
    PersonalDataCategory.CREDENTIALS: (
        "Troque imediatamente sua senha de acesso ao Índice e em qualquer outro serviço em que "
        "a mesma senha tenha sido utilizada."
    ),
    PersonalDataCategory.PROFESSIONAL: (
        "Fique atento(a) a contatos que usem informações sobre seu cargo ou área para parecer "
        "legítimos."
    ),
    PersonalDataCategory.ACCESS_HISTORY: (
        "Revise suas atividades recentes no sistema e comunique qualquer acesso que não reconheça."
    ),
    PersonalDataCategory.DOCUMENT_CONTENT: (
        "Não repasse documentos técnicos recebidos de fontes não confirmadas e comunique qualquer "
        "tentativa de obtê-los indevidamente."
    ),
    PersonalDataCategory.OTHER: (
        "Permaneça atento(a) a qualquer uso indevido de suas informações."
    ),
}

GENERAL_GUIDANCE = (
    "Comunique imediatamente qualquer suspeita de uso indevido de suas informações pelo canal "
    "indicado abaixo."
)


def _active(users):
    return [user for user in users if user is not None and user.is_active]


def identify_affected_users(incident) -> list:
    recipients = {}

    def include(users, reason):
        for user in _active(users):
            recipients.setdefault(user.pk, (user, reason))

    include(
        incident.affected_users.order_by("name", "id"),
        SubjectNotificationReason.AFFECTED_USER,
    )
    documents = list(
        incident.affected_documents.select_related("responsible", "created_by").order_by("id")
    )
    include(
        [document.responsible for document in documents],
        SubjectNotificationReason.DOCUMENT_RESPONSIBLE,
    )
    include(
        [document.created_by for document in documents],
        SubjectNotificationReason.DOCUMENT_CREATOR,
    )
    revisions = (
        Revision.objects.filter(document__in=documents)
        .select_related("author")
        .order_by("document_id", "version")
    )
    include(
        [revision.author for revision in revisions],
        SubjectNotificationReason.REVISION_AUTHOR,
    )
    accesses = (
        DocumentAccess.objects.filter(document__in=documents)
        .select_related("user")
        .order_by("document_id", "id")
    )
    include([access.user for access in accesses], SubjectNotificationReason.DOCUMENT_ACCESS)
    return list(recipients.values())


def _incident(incident_id):
    incident = DataIncident.objects.filter(pk=incident_id).first()
    if incident is None:
        raise IncidentNotFoundError()
    return incident


def recorded_recipients(incident) -> list:
    return list(
        incident.subject_notifications.select_related("user").order_by("user__name", "user_id")
    )


def sync_recipients(incident) -> list:
    known = set(incident.subject_notifications.values_list("user_id", flat=True))
    DataIncidentSubjectNotification.objects.bulk_create(
        [
            DataIncidentSubjectNotification(incident=incident, user=user, reason=reason)
            for user, reason in identify_affected_users(incident)
            if user.pk not in known
        ]
    )
    return recorded_recipients(incident)


def planned_recipients(incident) -> list:
    rows = {row.user_id: row for row in recorded_recipients(incident)}
    for user, reason in identify_affected_users(incident):
        rows.setdefault(
            user.pk, DataIncidentSubjectNotification(incident=incident, user=user, reason=reason)
        )
    return sorted(rows.values(), key=lambda row: (row.user.name, row.user_id))


def is_deliverable(row) -> bool:
    return row.status != SubjectNotificationStatus.SENT and row.attempts < MAX_ATTEMPTS


def summarize(rows) -> dict:
    return {
        "identified": len(rows),
        "sent": sum(row.status == SubjectNotificationStatus.SENT for row in rows),
        "failed": sum(row.status == SubjectNotificationStatus.FAILED for row in rows),
        "pending": sum(row.status == SubjectNotificationStatus.PENDING for row in rows),
        "exhausted": sum(
            row.status == SubjectNotificationStatus.FAILED and row.attempts >= MAX_ATTEMPTS
            for row in rows
        ),
    }


def _format(moment) -> str:
    return timezone.localtime(moment).strftime("%d/%m/%Y às %H:%M")


def message_context(incident, recipient_name=None) -> dict:
    categories = [
        category
        for category in incident.affected_data_categories
        if category in DATA_CATEGORY_LABELS
    ]
    measures = incident.actions.filter(kind__in=MEASURE_KINDS).order_by("performed_at", "id")
    return {
        "recipient_name": recipient_name,
        "reference": incident.reference,
        "title": incident.title,
        "incident_type_label": INCIDENT_TYPE_LABELS.get(
            incident.incident_type, incident.incident_type
        ),
        "occurred_at": _format(incident.occurred_at),
        "detected_at": _format(incident.detected_at),
        "data_category_labels": [DATA_CATEGORY_LABELS[category] for category in categories],
        "measures": [action.description for action in measures],
        "guidance": [DATA_CATEGORY_GUIDANCE[category] for category in categories]
        + [GENERAL_GUIDANCE],
        "authority_notification_required": incident.authority_notification_required,
        "authority_notified": incident.authority_notified_at is not None,
        "contact_email": settings.INCIDENT_CONTACT_EMAIL,
    }


def render_message(incident, recipient_name=None) -> dict:
    context = message_context(incident, recipient_name)
    return {
        "subject": f"{SUBJECT_PREFIX} {incident.reference}",
        "text": render_to_string(TEXT_TEMPLATE, context),
        "html": render_to_string(HTML_TEMPLATE, context),
    }


def _deliver(row, incident) -> bool:
    message = render_message(incident, row.user.name)
    email = EmailMultiAlternatives(
        message["subject"], message["text"], settings.DEFAULT_FROM_EMAIL, [row.user.email]
    )
    email.attach_alternative(message["html"], "text/html")
    row.attempts += 1
    row.last_attempt_at = timezone.now()
    try:
        email.send()
    except Exception as exc:
        logger.exception(
            "Could not send the communication of %s to user %s", incident.reference, row.user_id
        )
        row.status = SubjectNotificationStatus.FAILED
        row.last_error = type(exc).__name__[:100]
        row.save(update_fields=["attempts", "last_attempt_at", "status", "last_error"])
        return False
    row.status = SubjectNotificationStatus.SENT
    row.sent_at = row.last_attempt_at
    row.last_error = ""
    row.save(update_fields=["attempts", "last_attempt_at", "status", "sent_at", "last_error"])
    return True


def _send_deliverable(incident, rows) -> dict:
    outcome = {"sent": 0, "failed": 0, "skipped": 0}
    for row in rows:
        if not is_deliverable(row):
            outcome["skipped"] += 1
            continue
        outcome["sent" if _deliver(row, incident) else "failed"] += 1
    everyone_notified = bool(rows) and all(
        row.status == SubjectNotificationStatus.SENT for row in rows
    )
    if everyone_notified and incident.subjects_notified_at is None:
        incident.subjects_notified_at = timezone.now()
        incident.save(update_fields=["subjects_notified_at", "updated_at"])
    return outcome


def notify_affected_users(incident_id) -> dict:
    incident = _incident(incident_id)
    if incident.status == IncidentStatus.CLOSED:
        raise IncidentClosedError()
    rows = sync_recipients(incident)
    if not rows:
        raise NoAffectedUsersError()
    outcome = _send_deliverable(incident, rows)
    return {
        "incident": incident,
        "recipients": rows,
        "summary": summarize(rows),
        "preview": render_message(incident),
        "outcome": outcome,
    }


def subject_notifications_overview(incident_id) -> dict:
    incident = _incident(incident_id)
    rows = planned_recipients(incident)
    return {
        "incident": incident,
        "recipients": rows,
        "summary": summarize(rows),
        "preview": render_message(incident),
    }


def retry_subject_notifications(incident_id=None) -> list:
    incidents = (
        DataIncident.objects.exclude(status=IncidentStatus.CLOSED)
        .filter(
            subject_notifications__status__in=[
                SubjectNotificationStatus.PENDING,
                SubjectNotificationStatus.FAILED,
            ],
            subject_notifications__attempts__lt=MAX_ATTEMPTS,
        )
        .distinct()
        .order_by("id")
    )
    if incident_id is not None:
        incidents = incidents.filter(pk=incident_id)
    return [
        {
            "incident": incident,
            "outcome": _send_deliverable(incident, recorded_recipients(incident)),
        }
        for incident in incidents
    ]
