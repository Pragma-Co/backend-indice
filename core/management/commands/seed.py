"""Load the demonstration dataset (see _seed_data.py).

Idempotent: every row is matched by its natural key, so running the command
twice creates nothing new and changes no password. Everything happens in one
transaction, so a failure halfway through leaves the database untouched.

    docker compose exec api python manage.py seed

The one exception to idempotency is `audit_log`, which is append-only at the
database level and has no natural key — those rows are written only when the
table is still empty.
"""

import hashlib
import os
import random
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.management.commands import _seed_data as data
from core.models import (
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    Tag,
    User,
)


class Command(BaseCommand):
    help = "Load a demonstration dataset for an aerostructures manufacturer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help=(
                "Password for every seeded user. Falls back to SEED_PASSWORD, "
                "then to a random one printed at the end."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow seeding while DEBUG is off. Demo data is not production data.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG is off, so this looks like a real deployment. "
                "Re-run with --force if you really want demo data here."
            )

        password = options["password"] or os.environ.get("SEED_PASSWORD")
        generated_password = password is None
        if generated_password:
            password = secrets.token_urlsafe(12)

        self.now = timezone.now()
        self.created = {}

        areas = self._seed_areas()
        users = self._seed_users(areas, password)
        self._assign_managers(areas, users)
        disciplines = self._seed_disciplines()
        document_types = self._seed_document_types()
        projects = self._seed_projects(disciplines)
        tags = self._seed_tags()
        documents = self._seed_documents(
            projects, disciplines, document_types, users, areas, tags
        )
        revisions = self._seed_revisions(documents, users)
        self._seed_files(documents, revisions)
        accesses = self._seed_document_access(documents, users)
        self._seed_audit_log(users, documents, revisions, accesses)

        self._report(generated_password, password)

    # -- helpers --------------------------------------------------------------

    def _count(self, label, created):
        entry = self.created.setdefault(label, [0, 0])
        entry[0 if created else 1] += 1

    def _ago(self, days):
        return self.now - timedelta(days=days)

    # -- organization ---------------------------------------------------------

    def _seed_areas(self):
        areas = {}
        for acronym, name, _manager, active in data.AREAS:
            area, created = Area.objects.get_or_create(
                acronym=acronym,
                defaults={"name": name, "active": active},
            )
            self._count("area", created)
            areas[acronym] = area
        return areas

    def _seed_users(self, areas, password):
        users = {}
        for key, name, role, area_acronym, active in data.USERS:
            email = f"{key}@{data.EMAIL_DOMAIN}"
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    name=name,
                    role=role,
                    area=areas[area_acronym],
                    is_active=active,
                )
                self._count("app_user", True)
            else:
                self._count("app_user", False)
            users[key] = user
        return users

    def _assign_managers(self, areas, users):
        """`area.manager` must be a member of the area — rule 1 of section 8."""
        for acronym, _name, manager_key, _active in data.AREAS:
            if manager_key is None:
                continue
            area, manager = areas[acronym], users[manager_key]
            if manager.area_id != area.pk:
                raise CommandError(
                    f"{manager.email} cannot manage {acronym}: they belong to "
                    f"another area."
                )
            if area.manager_id != manager.pk:
                area.manager = manager
                area.save(update_fields=["manager"])

    # -- catalogs -------------------------------------------------------------

    def _seed_disciplines(self):
        disciplines = {}
        for code, name, active in data.DISCIPLINES:
            discipline, created = Discipline.objects.get_or_create(
                code=code, defaults={"name": name, "active": active}
            )
            self._count("discipline", created)
            disciplines[code] = discipline
        return disciplines

    def _seed_document_types(self):
        document_types = {}
        for code, name, active in data.DOCUMENT_TYPES:
            document_type, created = DocumentType.objects.get_or_create(
                code=code, defaults={"name": name, "active": active}
            )
            self._count("document_type", created)
            document_types[code] = document_type
        return document_types

    def _seed_projects(self, disciplines):
        projects = {}
        for code, name, active, discipline_codes in data.PROJECTS:
            project, created = Project.objects.get_or_create(
                code=code, defaults={"name": name, "active": active}
            )
            self._count("project", created)
            # set() is idempotent and writes straight to project_discipline
            project.disciplines.set([disciplines[c] for c in discipline_codes])
            projects[code] = project
        return projects

    def _seed_tags(self):
        tags = {}
        for name in data.TAGS:
            tag, created = Tag.objects.get_or_create(name=name)
            self._count("tag", created)
            tags[name] = tag
        return tags

    # -- documents ------------------------------------------------------------

    def _seed_documents(self, projects, disciplines, document_types, users, areas, tags):
        documents = {}
        for row in data.DOCUMENTS:
            (
                code,
                title,
                description,
                project_code,
                discipline_code,
                type_code,
                confidentiality,
                responsible_key,
                area_acronyms,
                tag_names,
                created_days_ago,
            ) = row

            project = projects[project_code]
            discipline = disciplines[discipline_code]

            # Rule 2 of section 8: the discipline must be one of the project's
            if not project.project_disciplines.filter(discipline=discipline).exists():
                raise CommandError(
                    f"{code}: discipline {discipline_code} is not part of "
                    f"project {project_code}."
                )
            # Rule 4: a document needs at least one area
            if not area_acronyms:
                raise CommandError(f"{code}: a document needs at least one area.")

            document, created = Document.objects.get_or_create(
                code=code,
                defaults={
                    "title": title,
                    "description": description,
                    "project": project,
                    "discipline": discipline,
                    "document_type": document_types[type_code],
                    "confidentiality_level": confidentiality,
                    "responsible": users[responsible_key],
                    "created_at": self._ago(created_days_ago),
                    "updated_at": self._ago(created_days_ago),
                },
            )
            self._count("document", created)
            document.areas.set([areas[a] for a in area_acronyms])
            document.tags.set([tags[t] for t in tag_names])
            documents[code] = document
        return documents

    def _seed_revisions(self, documents, users):
        revisions = {}
        for code, plan in data.REVISIONS.items():
            document = documents[code]
            for (
                version,
                status,
                author_key,
                auditor_key,
                created_days_ago,
                audited_days_ago,
                change_description,
                auditor_comment,
            ) in plan:
                author = users[author_key]
                auditor = users[auditor_key] if auditor_key else None

                # Rule 3 of section 8: the auditor is never the author
                if auditor is not None and auditor.pk == author.pk:
                    raise CommandError(
                        f"{code} v{version}: {author.email} cannot audit their "
                        f"own revision."
                    )

                audited_at = (
                    self._ago(audited_days_ago) if audited_days_ago is not None else None
                )
                # A revision is issued when it leaves the pending state
                issue_date = (
                    audited_at.date()
                    if status in (RevisionStatus.APPROVED, RevisionStatus.OBSOLETE)
                    else None
                )
                revision, created = Revision.objects.get_or_create(
                    document=document,
                    version=version,
                    defaults={
                        "status": status,
                        "issue_date": issue_date,
                        "change_description": change_description,
                        "author": author,
                        "auditor": auditor,
                        "auditor_comment": auditor_comment,
                        "audited_at": audited_at,
                        "created_at": self._ago(created_days_ago),
                    },
                )
                self._count("revision", created)
                revisions[(code, version)] = revision
        return revisions

    def _seed_files(self, documents, revisions):
        for (code, version), revision in revisions.items():
            type_code = documents[code].document_type.code
            for suffix, extension in data.FILES_BY_TYPE[type_code]:
                filename = f"{code.lower()}{suffix}.{extension}"
                storage_path = f"documents/{code}/v{version}/{filename}"
                low, high = data.SIZE_RANGES[extension]
                _, created = File.objects.get_or_create(
                    storage_path=storage_path,
                    defaults={
                        "revision": revision,
                        "original_name": filename,
                        "extension": extension,
                        "mime_type": data.MIME_TYPES[extension],
                        # Deterministic so a re-run finds the very same row
                        "size_bytes": random.Random(storage_path).randint(low, high),
                        "sha256": hashlib.sha256(storage_path.encode()).hexdigest(),
                        "uploaded_at": revision.created_at,
                    },
                )
                self._count("file", created)

    def _seed_document_access(self, documents, users):
        accesses = []
        for (
            code,
            user_key,
            status,
            approver_key,
            requested_days_ago,
            decided_days_ago,
            justification,
        ) in data.DOCUMENT_ACCESS:
            document = documents[code]
            approver = users[approver_key] if approver_key else None

            # Rule 5 of section 8: only the responsible or the manager of one of
            # the document's areas decides a request
            if approver is not None:
                deciders = {document.responsible_id} | set(
                    document.areas.exclude(manager=None).values_list(
                        "manager_id", flat=True
                    )
                )
                if approver.pk not in deciders:
                    raise CommandError(
                        f"{code}: {approver.email} is neither the responsible "
                        f"nor the manager of one of its areas."
                    )

            access, created = DocumentAccess.objects.get_or_create(
                document=document,
                user=users[user_key],
                defaults={
                    "status": status,
                    "justification": justification,
                    "requested_at": (
                        self._ago(requested_days_ago)
                        if requested_days_ago is not None
                        else None
                    ),
                    "approver": approver,
                    "decided_at": (
                        self._ago(decided_days_ago)
                        if decided_days_ago is not None
                        else None
                    ),
                },
            )
            self._count("document_access", created)
            accesses.append(access)
        return accesses

    # -- audit trail ----------------------------------------------------------

    def _seed_audit_log(self, users, documents, revisions, accesses):
        """Write the trail only on the first run.

        `audit_log` rejects UPDATE and DELETE at the database level and has no
        natural key to match on, so re-seeding would only pile up duplicates.
        """
        if AuditLog.objects.exists():
            self.created["audit_log"] = [0, AuditLog.objects.count()]
            return

        rng = random.Random("audit")
        entries = []

        def entry(user, action, entity, entity_id, occurred_at, record=None):
            entries.append(
                AuditLog(
                    user=user,
                    action=action,
                    entity=entity,
                    entity_id=entity_id,
                    # A READ carries no snapshot — there was nothing to change
                    record=None if action == AuditAction.READ else record,
                    ip_address=f"10.20.{rng.randint(1, 6)}.{rng.randint(10, 240)}",
                    occurred_at=occurred_at,
                )
            )

        for user in users.values():
            if user.is_active:
                entry(
                    user,
                    AuditAction.LOGIN,
                    "app_user",
                    user.pk,
                    self._ago(rng.randint(0, 14)),
                )

        for document in documents.values():
            entry(
                document.responsible,
                AuditAction.CREATE,
                "document",
                document.pk,
                document.created_at,
                {"code": document.code, "title": document.title},
            )

        for revision in revisions.values():
            entry(
                revision.author,
                AuditAction.CREATE,
                "revision",
                revision.pk,
                revision.created_at,
                {"document_id": revision.document_id, "version": revision.version},
            )
            if revision.audited_at is not None:
                entry(
                    revision.auditor,
                    AuditAction.UPDATE,
                    "revision",
                    revision.pk,
                    revision.audited_at,
                    {"version": revision.version, "status": revision.status},
                )

        for access in accesses:
            if access.requested_at is not None:
                entry(
                    access.user,
                    AuditAction.CREATE,
                    "document_access",
                    access.pk,
                    access.requested_at,
                    {"document_id": access.document_id, "status": "PENDING"},
                )
            if access.decided_at is not None:
                entry(
                    access.approver,
                    AuditAction.UPDATE,
                    "document_access",
                    access.pk,
                    access.decided_at,
                    {"document_id": access.document_id, "status": access.status},
                )

        readers = [u for u in users.values() if u.is_active]
        for document in list(documents.values())[:12]:
            for reader in rng.sample(readers, 2):
                entry(
                    reader,
                    AuditAction.READ,
                    "document",
                    document.pk,
                    self._ago(rng.randint(1, 45)),
                )

        # A document that no longer exists: the trail outlives its target,
        # because audit_log has no foreign key to it (section 7)
        entry(
            users["marina.duarte"],
            AuditAction.DELETE,
            "document",
            max(d.pk for d in documents.values()) + 137,
            self._ago(88),
            {
                "code": "AK-1500-MAT-ESP-0002",
                "title": "Especificação de nacele substituída",
                "confidentiality_level": "CONFIDENTIAL",
            },
        )

        AuditLog.objects.bulk_create(entries)
        for _ in entries:
            self._count("audit_log", True)

    # -- output ---------------------------------------------------------------

    def _report(self, generated_password, password):
        self.stdout.write("")
        self.stdout.write(f"{'table':<18}{'created':>9}{'existing':>10}")
        self.stdout.write("-" * 37)
        for label, (created, existing) in self.created.items():
            self.stdout.write(f"{label:<18}{created:>9}{existing:>10}")
        self.stdout.write("")

        approved = Revision.objects.filter(status=RevisionStatus.APPROVED).count()
        self.stdout.write(
            f"{Document.objects.count()} documents, "
            f"{approved} of them with a current revision."
        )

        example = f"marina.duarte@{data.EMAIL_DOMAIN}"
        if self.created.get("app_user", [0, 0])[0] == 0:
            # Nothing was created, so no password was applied to anybody
            self.stdout.write(
                f"No new users, so existing passwords were left untouched. "
                f"Log in with an email, for example {example} (role ADMIN)."
            )
        elif generated_password:
            self.stdout.write(
                self.style.WARNING(
                    f"\nSeeded users share this generated password: {password}\n"
                    f"Set SEED_PASSWORD in your .env to choose it yourself.\n"
                    f"Log in with an email, for example {example} (role ADMIN)."
                )
            )
        else:
            self.stdout.write(
                f"Seeded users share the password you supplied. Log in with an "
                f"email, for example {example} (role ADMIN)."
            )
        self.stdout.write(self.style.SUCCESS("\nSeed complete."))
