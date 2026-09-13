from django.core.management.base import BaseCommand, CommandError
from exporter.client import ConfluenceClient, ExportError

class Command(BaseCommand):
    help = "PAT kimliği ve space API erişimini kontrol eder."
    def handle(self, *args, **options):
        client = None
        try:
            client = ConfluenceClient()
            user = client.json("rest/api/user/current")
            if user.get("type") != "known":
                raise ExportError("PAT doğrulanamadı; anonim veya beklenmeyen kullanıcı yanıtı.")
            spaces = client.json("rest/api/space", params={"limit": 1})
            if not isinstance(spaces.get("results"), list):
                raise ExportError("Space API yanıtı beklenenden farklı.")
            self.stdout.write(self.style.SUCCESS("PAT doğrulandı; Confluence API erişimi başarılı."))
            if not spaces["results"]:
                self.stdout.write("Görünür space bulunamadı; hesabın izinlerini kontrol edin.")
        except ExportError as exc:
            raise CommandError(str(exc)) from None
        finally:
            if client:
                client.session.close()
