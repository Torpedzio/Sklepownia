from django.core.management.base import BaseCommand

from monitoring import checks


class Command(BaseCommand):
    help = (
        "Sprawdza teraz sklepy i usługi serwera sklepów, tak jak monitor co kilka minut: liczy awarie, naprawia "
        "i powiadamia. Uruchamiaj w kontenerze workera, który ma dostęp do Dockera."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="Tylko te sklepy (adresy); domyślnie wszystkie działające.")

    def handle(self, *args, slugs, **options):
        result = checks.run(slugs=slugs or None)
        for name, problem in sorted(result.services.items()):
            self.stderr.write(f"{name}: {problem}")
        if result.skipped:
            self.stderr.write(result.skipped)
        for shop, problem in result.failing:
            self.stderr.write(f"{shop.slug}: {problem}")
        if result.checked:
            works = result.checked - len(result.failing)
            self.stdout.write(self.style.SUCCESS(f"Sprawdzone sklepy: {result.checked}, działa {works}."))
