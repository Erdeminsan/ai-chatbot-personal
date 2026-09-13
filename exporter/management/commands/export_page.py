from django.core.management.base import BaseCommand, CommandError
from exporter.client import ConfluenceClient, ExportError
from exporter.service import export_page
from exporter.enrichment import EnrichmentOptions

class Command(BaseCommand):
    help = 'Tek sayfayı, ekleri, isteğe bağlı OCR ve görsel yorumuyla dışa aktarır.'
    def add_arguments(self, parser):
        parser.add_argument('--page-id', required=True)
        parser.add_argument('--output', default='exports')
        parser.add_argument('--ocr', action='store_true')
        parser.add_argument('--ocr-lang', default='tur+eng')
        parser.add_argument('--vision', action='store_true')
        parser.add_argument('--resume', action='store_true')
    def handle(self, *args, **options):
        client = None
        try:
            enrichment = EnrichmentOptions(options['ocr'], options['ocr_lang'], options['vision'])
            enrichment.validate()
            client = ConfluenceClient()
            destination, issues = export_page(client, options['page_id'], options['output'],
                                             options=enrichment, resume=options['resume'])
            self.stdout.write(self.style.SUCCESS(f'Çıktı: {destination}'))
            self.stdout.write(f'Uyarılar: {len(issues)}. Ayrıntılar normalized.json içinde.')
        except (ExportError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from None
        finally:
            if client:
                client.session.close()
