"""Forms for short, touch-friendly CSRS workflows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
from typing import Any, cast

from django import forms
from django.db.models import Q

from accounts.models import User
from work.models import (
    InstitutionalAction,
    TaskProposal,
    WorkCalendar,
    default_work_calendar_id,
)
from work.services import (
    active_lines,
    can_self_assign,
    due_date_for,
    week_start_for,
    workload_for,
)


class DateInput(forms.DateInput):
    """French date input with an unambiguous visible and submitted value."""

    input_type = "text"

    def __init__(self, attrs: dict[str, object] | None = None) -> None:
        defaults: dict[str, object] = {
            "placeholder": "jj/mm/aaaa",
            "inputmode": "numeric",
            "maxlength": 10,
            "data-date-input": "",
        }
        defaults.update(attrs or {})
        super().__init__(attrs=defaults, format="%d/%m/%Y")


class WorkloadInput(forms.NumberInput):
    """Render integer or one-decimal workloads without trailing zeroes."""

    def __init__(self, attrs: dict[str, object] | None = None) -> None:
        defaults: dict[str, object] = {"step": "0.1", "inputmode": "decimal"}
        defaults.update(attrs or {})
        super().__init__(attrs=defaults)

    def format_value(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        try:
            normalized = Decimal(str(value)).quantize(Decimal("0.1"))
        except InvalidOperation:
            return str(value)
        return format(normalized.normalize(), "f")


def default_calendar() -> WorkCalendar:
    """Return the currently configured creation calendar."""
    return WorkCalendar.objects.get(pk=default_work_calendar_id())


def setup_schedule_fields(form: forms.BaseForm, calendar: WorkCalendar) -> None:
    """Attach non-authoritative client hints for synchronized date/workload inputs."""
    overrides = {
        item.day.isoformat(): item.is_working_day for item in calendar.days.all()
    }
    form.fields["schedule_source"] = forms.CharField(
        required=False, initial="workload", widget=forms.HiddenInput
    )
    form.fields["calendar_overrides"] = forms.CharField(
        required=False,
        initial=json.dumps(overrides),
        widget=forms.HiddenInput,
    )
    form.fields["due_date"].required = False
    form.fields["estimated_work_days"].required = False
    form.fields["due_date"].widget.attrs["data-schedule-due"] = ""
    form.fields["estimated_work_days"].widget.attrs["data-schedule-workload"] = ""
    form.fields["start_date"].widget.attrs["data-schedule-start"] = ""
    for field_name in ("start_date", "due_date"):
        date_field = cast(forms.DateField, form.fields[field_name])
        date_field.input_formats = ["%d/%m/%Y", "%Y-%m-%d"]


def clean_schedule(
    form: forms.BaseForm,
    cleaned: dict[str, object],
    calendar: WorkCalendar,
) -> dict[str, object]:
    """Normalize either accepted schedule pair with the last-edited field as source."""
    start = cleaned.get("start_date")
    due = cleaned.get("due_date")
    workload = cleaned.get("estimated_work_days")
    if not isinstance(start, date):
        return cleaned
    if not calendar.is_working_day(start):
        form.add_error("start_date", "Le debut doit etre un jour ouvre.")
    if not isinstance(due, date) and not isinstance(workload, Decimal):
        message = "Renseignez l'echeance ou la charge estimee."
        form.add_error("due_date", message)
        form.add_error("estimated_work_days", message)
        return cleaned
    source = str(cleaned.get("schedule_source") or "workload")
    if source == "due" and isinstance(due, date):
        if due <= start:
            form.add_error("due_date", "L'echeance doit suivre la date de debut.")
            return cleaned
        calculated_workload = workload_for(start, due, calendar)
        if calculated_workload <= 0:
            form.add_error("due_date", "L'echeance doit inclure un jour ouvre.")
            return cleaned
        cleaned["estimated_work_days"] = calculated_workload
    elif isinstance(workload, Decimal):
        cleaned["due_date"] = due_date_for(start, workload, calendar)
    return cleaned


class AssignmentCreateForm(forms.Form):
    title = forms.CharField(label="Nom court", max_length=180)
    description = forms.CharField(
        label="Description", widget=forms.Textarea(attrs={"rows": 4})
    )
    employee = forms.ModelChoiceField(label="Collaborateur", queryset=User.objects.none())
    start_date = forms.DateField(label="Debut", widget=DateInput)
    due_date = forms.DateField(label="Echeance", widget=DateInput, required=False)
    estimated_work_days = forms.DecimalField(
        label="Charge estimee (jours ouvres)",
        min_value=Decimal("0.1"),
        decimal_places=1,
        required=False,
        widget=WorkloadInput,
    )
    action = forms.ModelChoiceField(
        label="Action institutionnelle (facultative)",
        queryset=InstitutionalAction.objects.filter(active=True),
        required=False,
        help_text="Classification optionnelle dans le plan d'action institutionnel.",
    )

    def __init__(
        self,
        *args: Any,
        manager: User,
        calendar: WorkCalendar | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.calendar = calendar or default_calendar()
        setup_schedule_fields(self, self.calendar)
        employee_field = cast(forms.ModelChoiceField, self.fields["employee"])
        line_filter = active_lines().filter(supervisor=manager, is_primary=True)
        allowed_filter = Q(reporting_lines__in=line_filter)
        if can_self_assign(manager):
            allowed_filter |= Q(pk=manager.pk)
        employee_field.queryset = User.objects.filter(allowed_filter).distinct()
        monday = week_start_for(date.today())
        while not self.calendar.is_working_day(monday):
            monday = date.fromordinal(monday.toordinal() + 1)
        self.fields["start_date"].initial = monday
        self.fields["estimated_work_days"].initial = Decimal("5.0")
        self.fields["due_date"].initial = due_date_for(
            monday, Decimal("5.0"), self.calendar
        )

    def clean(self) -> dict[str, object]:
        cleaned = super().clean() or {}
        return clean_schedule(self, cleaned, self.calendar)


class ProgressForm(forms.Form):
    percentage = forms.IntegerField(
        label="Avancement",
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(
            attrs={"type": "range", "min": 0, "max": 100, "step": 5, "data-progress": ""}
        ),
    )
    note = forms.CharField(
        label="Note sur cette progression",
        help_text="Facultative, sauf en cas de regression ou de point d'attention.",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    blocked = forms.BooleanField(label="Je suis bloque", required=False)

    def __init__(self, *args: Any, self_managed: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self_managed:
            self.fields["blocked"].label = "Signaler un point d'attention"

    def clean_percentage(self) -> int:
        percentage = cast(int, self.cleaned_data["percentage"])
        if percentage % 5:
            raise forms.ValidationError("Utilisez un pas de 5 %.")
        return percentage


class AssignmentEditForm(forms.Form):
    title = forms.CharField(label="Nom court", max_length=180)
    description = forms.CharField(
        label="Description", widget=forms.Textarea(attrs={"rows": 4})
    )
    start_date = forms.DateField(label="Debut", widget=DateInput)
    due_date = forms.DateField(label="Echeance", widget=DateInput, required=False)
    estimated_work_days = forms.DecimalField(
        label="Charge estimee (jours ouvres)",
        min_value=Decimal("0.1"),
        decimal_places=1,
        required=False,
        widget=WorkloadInput,
    )
    action = forms.ModelChoiceField(
        label="Action institutionnelle (facultative)",
        queryset=InstitutionalAction.objects.filter(active=True),
        required=False,
        help_text="Classification optionnelle dans le plan d'action institutionnel.",
    )

    def __init__(
        self,
        *args: Any,
        calendar: WorkCalendar | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.calendar = calendar or default_calendar()
        setup_schedule_fields(self, self.calendar)
        self.fields["schedule_source"].initial = "due"

    def clean(self) -> dict[str, object]:
        cleaned = super().clean() or {}
        return clean_schedule(self, cleaned, self.calendar)


class CommentForm(forms.Form):
    body = forms.CharField(
        label="Observation generale", widget=forms.Textarea(attrs={"rows": 3})
    )


class ProposalForm(forms.ModelForm):
    class Meta:
        model = TaskProposal
        fields = (
            "title",
            "description",
            "start_date",
            "due_date",
            "estimated_work_days",
            "action",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "start_date": DateInput(),
            "due_date": DateInput(),
            "estimated_work_days": WorkloadInput(),
        }

    def __init__(
        self,
        *args: Any,
        calendar: WorkCalendar | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.calendar = calendar or default_calendar()
        self.instance.calendar = self.calendar
        setup_schedule_fields(self, self.calendar)
        self.fields["action"].label = "Action institutionnelle (facultative)"
        self.fields[
            "action"
        ].help_text = "Classification optionnelle dans le plan d'action institutionnel."

    def clean(self) -> dict[str, object]:
        cleaned = super().clean() or {}
        return clean_schedule(self, cleaned, self.calendar)


class ReasonForm(forms.Form):
    reason = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 3}))
