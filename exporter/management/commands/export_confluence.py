from datetime import datetime, timezone
from django.core.management.base import BaseCommand, CommandError
from exporter.client import ConfluenceClient, ExportError
from exporter.crawler import crawl
from exporter.enrichment import EnrichmentOptions

class Command(BaseCommand):
    help = 'Tüm space, tek space veya bir sayfa ağacını JSON/Markdown olarak dışa aktarır.'
    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument('--all-spaces', action='store_true')
        scope.add_argument('--space-key')
        scope.add_argument('--root-page-id')
        parser.add_argument('--include-archived-spaces', action='store_true')
        parser.add_argument('--output', default=None)
        parser.add_argument('--resume', action='store_true')
        parser.add_argument('--ocr', action='store_true')
        parser.add_argument('--ocr-lang', default='tur+eng')
        parser.add_argument('--vision', action='store_true')
    def handle(self, *args, **options):
        client = None
        try:
            if options['resume'] and not options['output']:
                raise ExportError('--resume ile önceki --output klasörünü belirtin.')
            enrichment = EnrichmentOptions(options['ocr'], options['ocr_lang'], options['vision'])
            enrichment.validate()
            client = ConfluenceClient()
            output = options['output'] or 'exports_batch/' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            self.stdout.write(f'Tarama çıktısı: {output}')
            summary = crawl(client, output, all_spaces=options['all_spaces'], space_key=options['space_key'],
                            root_page_id=options['root_page_id'], include_archived_spaces=options['include_archived_spaces'],
                            resume=options['resume'], options=enrichment, progress=self.stdout.write)
            self.stdout.write(f"Kaydedilen: {summary['exported']}, tekrar kullanılan: {summary['reused']}, "
                              f"uyarılı: {summary['needs_review']}, hata: {summary['failed']}, "
                              f"listeleme hatası: {summary['enumeration_errors']}")
            if summary['status'] != 'completed':
                raise ExportError('Tarama kısmen tamamlandı; run-*.jsonl raporunu inceleyin.')
        except (ExportError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from None
        finally:
            if client:
                client.session.close()
