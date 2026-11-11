import time
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from exporter.client import ConfluenceClient, ExportError
from exporter.crawler import crawl
from exporter.enrichment import EnrichmentOptions
from retrieval.models import ExportJob

class Command(BaseCommand):
    help = 'Confluence panelindeki tarama kuyruğunu işler.'
    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--recover', action='store_true', help='Başka worker yokken yarım kalmış running görevlerini failed yapar.')
    def handle(self, **options):
        if options['recover']:
            ExportJob.objects.filter(status='running').update(status='failed', message='Önceki worker kesildi; yeni tarama başlatın.', updated_at=timezone.now())
        self.stdout.write('Panel worker hazır; Ctrl+C ile durdurabilirsiniz.')
        while True:
            job = ExportJob.objects.filter(status='queued').order_by('created_at').first()
            if job and ExportJob.objects.filter(pk=job.pk, status='queued').update(status='running', updated_at=timezone.now()):
                client = None
                def progress(message):
                    ExportJob.objects.filter(pk=job.pk).update(message=message, updated_at=timezone.now())
                try:
                    options_ = EnrichmentOptions(ocr=job.ocr, vision=job.vision)
                    options_.validate()
                    client = ConfluenceClient()
                    summary = crawl(client, settings.PANEL_EXPORT_ROOT / str(job.pk), all_spaces=job.scope == 'all',
                                    space_key=job.target if job.scope == 'space' else None,
                                    root_page_id=job.target if job.scope == 'tree' else None,
                                    options=options_, progress=progress)
                    ExportJob.objects.filter(pk=job.pk).update(status=summary['status'], summary=summary, message='Tarama sona erdi.', updated_at=timezone.now())
                except KeyboardInterrupt:
                    ExportJob.objects.filter(pk=job.pk).update(status='failed', message='Worker durduruldu; biten sayfalar saklandı.', updated_at=timezone.now())
                    return
                except Exception as exc:
                    message = str(exc) if isinstance(exc, ExportError) else f'İşlem hatası: {type(exc).__name__}'
                    ExportJob.objects.filter(pk=job.pk).update(status='failed', message=message, updated_at=timezone.now())
                finally:
                    if client:
                        client.session.close()
            elif options['once']:
                return
            else:
                try:
                    time.sleep(2)
                except KeyboardInterrupt:
                    return
            if options['once']:
                return
