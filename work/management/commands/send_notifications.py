"""Send bounded batches from the notification outbox."""

import time
from typing import cast

from django.core.management.base import BaseCommand, CommandParser

from work.notifications import deliver_due_notifications


class Command(BaseCommand):
    help = "Envoie les notifications email en attente avec reprises bornees."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=30)

    def handle(self, *args: object, **options: object) -> None:
        limit = max(1, min(200, cast(int, options["limit"])))
        interval = max(10, cast(int, options["interval"]))
        while True:
            result = deliver_due_notifications(limit)
            if result.sent or result.retried or result.failed:
                self.stdout.write(
                    f"notifications: sent={result.sent} retried={result.retried} failed={result.failed}"
                )
            if not cast(bool, options["watch"]):
                return
            time.sleep(interval)
