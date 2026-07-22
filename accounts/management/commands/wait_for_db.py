import time

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Wait for the database to become available before continuing (used in start.sh)."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=30, help="Max seconds to wait")

    def handle(self, *args, **options):
        self.stdout.write("Waiting for database...")
        timeout = options["timeout"]
        elapsed = 0
        while elapsed < timeout:
            try:
                connections["default"].cursor()
                self.stdout.write(self.style.SUCCESS("Database available."))
                return
            except OperationalError:
                time.sleep(1)
                elapsed += 1
        raise OperationalError(f"Database not available after {timeout}s")
