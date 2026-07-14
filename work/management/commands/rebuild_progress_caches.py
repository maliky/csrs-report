"""Pre-warm rebuildable progression-series caches."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from work.models import ProgressSeriesCache, TaskAssignment
from work.progress_cache import rebuild_progress_caches


class Command(BaseCommand):
    help = "Reconstruit les caches JSON des graphiques de progression."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--assignment",
            type=int,
            action="append",
            dest="assignment_ids",
            help="Limite la reconstruction a une affectation; option repetable.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Supprime les caches selectionnes avant reconstruction.",
        )

    def handle(self, *args: object, **options: object) -> None:
        del args
        assignment_ids = options.get("assignment_ids")
        queryset = TaskAssignment.objects.select_related("calendar").prefetch_related(
            "calendar__days", "progress_entries"
        )
        if isinstance(assignment_ids, list) and assignment_ids:
            queryset = queryset.filter(pk__in=assignment_ids)
        if options.get("clear"):
            caches = ProgressSeriesCache.objects.all()
            if isinstance(assignment_ids, list) and assignment_ids:
                caches = caches.filter(assignment_id__in=assignment_ids)
            caches.delete()
        count = rebuild_progress_caches(queryset)
        self.stdout.write(self.style.SUCCESS(f"{count} cache(s) reconstruit(s)."))
