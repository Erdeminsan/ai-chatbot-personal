import json
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from retrieval.backends import embedder, reranker
from retrieval.index import search_index
class Command(BaseCommand):
    help = 'Vektör top-K sonuçlarını CrossEncoder ile yeniden sıralar.'
    def add_arguments(self, parser):
        parser.add_argument('--query', required=True)
        parser.add_argument('--index', default=str(settings.RAG_INDEX_PATH))
        parser.add_argument('--k', type=int, default=20)
        parser.add_argument('--limit', type=int, default=5)
    def handle(self, **options):
        try:
            rows = search_index(options['index'], options['query'], embedder(), reranker(), options['k'], options['limit'])
        except Exception as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2))
