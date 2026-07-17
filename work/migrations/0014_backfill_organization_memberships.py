from django.db import migrations
from django.db.models import Q


def _unit_at(OrganizationMembership, ReportingLine, user_id, on_day):
    membership = (
        OrganizationMembership.objects.filter(
            user_id=user_id,
            is_primary=True,
            start_date__lte=on_day,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=on_day))
        .order_by("-start_date", "-pk")
        .first()
    )
    if membership is not None:
        return membership.unit_id
    line = (
        ReportingLine.objects.filter(
            employee_id=user_id,
            is_primary=True,
            start_date__lte=on_day,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=on_day))
        .order_by("-start_date", "-pk")
        .first()
    )
    return line.unit_id if line is not None else None


def backfill_organization(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    OrganizationMembership = apps.get_model("work", "OrganizationMembership")
    OrganizationUnitLink = apps.get_model("work", "OrganizationUnitLink")
    ReportingLine = apps.get_model("work", "ReportingLine")
    TaskAssignment = apps.get_model("work", "TaskAssignment")
    HistoricalTaskAssignment = apps.get_model("work", "HistoricalTaskAssignment")
    TaskProposal = apps.get_model("work", "TaskProposal")
    HistoricalTaskProposal = apps.get_model("work", "HistoricalTaskProposal")

    lines = ReportingLine.objects.select_related("employee").order_by(
        "employee_id", "start_date", "pk"
    )
    for line in lines.iterator():
        membership, created = OrganizationMembership.objects.get_or_create(
            user_id=line.employee_id,
            unit_id=line.unit_id,
            start_date=line.start_date,
            end_date=line.end_date,
            defaults={
                "job_title": line.employee.position,
                "is_primary": line.is_primary,
            },
        )
        if not created and line.is_primary and not membership.is_primary:
            open_primary = OrganizationMembership.objects.filter(
                user_id=line.employee_id,
                is_primary=True,
                end_date__isnull=True,
            ).exclude(pk=membership.pk)
            if line.end_date is not None or not open_primary.exists():
                membership.is_primary = True
                membership.save(update_fields=["is_primary"])

    supervisor_ids = ReportingLine.objects.values_list(
        "supervisor_id", flat=True
    ).distinct()
    for user in User.objects.filter(pk__in=supervisor_ids).iterator():
        if OrganizationMembership.objects.filter(
            user_id=user.pk, is_primary=True, end_date__isnull=True
        ).exists():
            continue
        supervised = list(
            ReportingLine.objects.filter(
                supervisor_id=user.pk,
                is_primary=True,
                end_date__isnull=True,
            ).values_list("unit_id", "start_date")
        )
        parent_ids = set(
            OrganizationUnitLink.objects.filter(
                collaborator_service_id__in=[unit_id for unit_id, _day in supervised]
            ).values_list("supervisor_service_id", flat=True)
        )
        if len(parent_ids) == 1 and supervised:
            OrganizationMembership.objects.create(
                user_id=user.pk,
                unit_id=parent_ids.pop(),
                job_title=user.position,
                start_date=min(day for _unit_id, day in supervised),
                is_primary=True,
            )

    for assignment in TaskAssignment.objects.filter(
        organization_unit__isnull=True
    ).iterator():
        unit_id = _unit_at(
            OrganizationMembership,
            ReportingLine,
            assignment.employee_id,
            assignment.start_date,
        )
        if unit_id is None:
            continue
        TaskAssignment.objects.filter(pk=assignment.pk).update(
            organization_unit_id=unit_id
        )
        HistoricalTaskAssignment.objects.filter(id=assignment.pk).update(
            organization_unit_id=unit_id
        )

    for proposal in TaskProposal.objects.filter(
        organization_unit__isnull=True
    ).iterator():
        unit_id = _unit_at(
            OrganizationMembership,
            ReportingLine,
            proposal.employee_id,
            proposal.start_date,
        )
        if unit_id is None:
            continue
        TaskProposal.objects.filter(pk=proposal.pk).update(
            organization_unit_id=unit_id
        )
        HistoricalTaskProposal.objects.filter(id=proposal.pk).update(
            organization_unit_id=unit_id
        )


def clear_backfill(apps, schema_editor):
    apps.get_model("work", "HistoricalTaskAssignment").objects.update(
        organization_unit_id=None
    )
    apps.get_model("work", "HistoricalTaskProposal").objects.update(
        organization_unit_id=None
    )
    apps.get_model("work", "TaskAssignment").objects.update(
        organization_unit_id=None
    )
    apps.get_model("work", "TaskProposal").objects.update(
        organization_unit_id=None
    )
    apps.get_model("work", "OrganizationMembership").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("work", "0013_historicaltaskassignment_organization_unit_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_organization, reverse_code=clear_backfill),
    ]
