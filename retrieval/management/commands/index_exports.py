from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from retrieval.backends import embedder
from retrieval.index import build_index
class Command(BaseCommand):
    help = 'normalized.json çıktılarından %10 örtüşmeli vektör indeksi üretir.'
    def add_arguments(self, parser):
        parser.add_argument('--input', required=True)
        parser.add_argument('--index', default=str(settings.RAG_INDEX_PATH))
        parser.add_argument('--chunk-size', type=int, default=800)
    def handle(self, **options):
        try:
            result = build_index(options['input'], options['index'], embedder(), options['chunk_size'])
        except Exception as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS(f"{result['documents']} belge, {result['chunks']} parça indekslendi."))
