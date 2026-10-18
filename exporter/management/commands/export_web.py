from django.core.management.base import BaseCommand, CommandError

from exporter.client import ExportError
from exporter.enrichment import EnrichmentOptions
from exporter.web import export_web
from exporter.web_client import WebClient


class Command(BaseCommand):
    help = 'Bir web sayfasını görsel/açıklama bağlamını koruyarak Markdown olarak kaydeder.'

    def add_arguments(self, parser):
        parser.add_argument('--url', required=True)
        parser.add_argument('--output', default='exports_web')
        parser.add_argument('--selector', help='Ana içerik için isteğe bağlı CSS seçicisi.')
        parser.add_argument('--ocr', action='store_true')
        parser.add_argument('--ocr-lang', default='tur+eng')
        parser.add_argument('--vision', action='store_true')

    def handle(self, *args, **options):
        client = None
        try:
            enrichment = EnrichmentOptions(options['ocr'], options['ocr_lang'], options['vision'])
            enrichment.validate()
            client = WebClient()
            target, warnings = export_web(client, options['url'], options['output'],
                                          selector=options['selector'], options=enrichment)
            self.stdout.write(self.style.SUCCESS(f'Markdown: {target / "page.md"}'))
            self.stdout.write(f'Uyarılar: {len(warnings)}; ayrıntılar normalized.json içinde.')
        except (ExportError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from None
        finally:
            if client:
                client.close()
