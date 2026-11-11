import json
import tempfile
from pathlib import Path
from unittest import TestCase as UnitTestCase
from unittest.mock import patch
import numpy as np
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from .chunking import chunk_text, encoding
from .index import build_index, search_index, read_documents
from .backends import RetrievalError, windows, LocalEmbedder, LocalReranker
from .models import ExportJob

class ChunkTests(UnitTestCase):
    def test_sizes_overlap_and_lossless_coverage(self):
        enc = encoding()
        for count in [1, 499, 500, 800, 1000, 1001, 1100, 1500, 1801, 5000]:
            text = ' word' * count
            parts = chunk_text(text)
            source = enc.encode(text, disallowed_special=())
            rebuilt = []
            for i, part in enumerate(parts):
                self.assertEqual(part['text'], enc.decode(source[part['token_start']:part['token_end']]))
                self.assertTrue(part['short_document'] or 500 <= part['token_count'] <= 1000)
                self.assertLessEqual(len(enc.encode(part['text'])), 1000)
                if i:
                    previous = parts[i-1]
                    self.assertEqual(part['overlap_from_previous'], previous['token_count'] // 10)
                    self.assertEqual(part['token_start'], previous['token_end'] - previous['token_count']//10)
                rebuilt.extend(source[part['token_start']+part['overlap_from_previous']:part['token_end']])
            self.assertEqual(rebuilt, source)
    def test_unicode_and_literal_special_tokens(self):
        text = 'İstanbul 🌍 中文 test <|endoftext|>\n' * 300
        parts = chunk_text(text)
        raw = text.encode()
        for part in parts:
            self.assertNotIn('\ufffd', part['text'])
            self.assertEqual(raw[part['byte_start']:part['byte_end']].decode(), part['text'])
    def test_blank_and_invalid_size(self):
        self.assertEqual(chunk_text('  '), [])
        for target in (499, 1001, 755):
            with self.assertRaises(ValueError):
                chunk_text('word', target)

class FakeEmbedder:
    signature = 'test-vectors-v1'
    def encode(self, texts, query=False):
        if query:
            return [[1., 0.]]
        return [[1., 0.] if 'alpha' in t else [0.8, 0.6] if 'beta' in t else [0., 1.] for t in texts]

class FakeReranker:
    def __init__(self):
        self.received = []
    def score(self, query, documents):
        self.received = documents
        return [10 if 'beta' in t else -1 for t in documents]

class IndexTests(UnitTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ['alpha','beta','gamma']:
            p = self.root / name
            p.mkdir()
            (p/'normalized.json').write_text(json.dumps({'source_type':'web','source_url':f'https://example.com/{name}', 'title': name,'markdown':name}))
        self.index = self.root/'index.sqlite3'
        build_index(self.root, self.index, FakeEmbedder())
    def test_top_k_then_crossencoder_changes_ranking(self):
        ranker=FakeReranker()
        result=search_index(self.index, 'question', FakeEmbedder(),ranker,k=2,limit=2)
        self.assertEqual(len(ranker.received),2)
        self.assertNotIn('gamma',ranker.received)
        self.assertEqual([row['title'] for row in result],['beta','alpha'])
        self.assertEqual(result[0]['vector_rank'],2)
        self.assertEqual(result[0]['rerank_rank'],1)
    def test_k_larger_than_corpus(self):
        ranker=FakeReranker()
        self.assertEqual(len(search_index(self.index,'test',FakeEmbedder(),ranker,k=20,limit=5)),3)
    def test_invalid_k_and_mismatched_model(self):
        for k,limit in [(0,1),(101,5),(2,3)]:
            with self.assertRaises(RetrievalError):
                search_index(self.index,'q',FakeEmbedder(),FakeReranker(),k,limit)
        model=FakeEmbedder();model.signature='other'
        with self.assertRaises(RetrievalError):
            search_index(self.index,'q',model,FakeReranker())
    def test_no_silent_fallback_after_rerank_failure(self):
        class Broken:
            def score(self, *args):
                raise RuntimeError('model error')
        with self.assertRaises(RuntimeError):
            search_index(self.index,'q',FakeEmbedder(),Broken())
    def test_failed_rebuild_preserves_previous_index(self):
        before=self.index.read_bytes()
        class Broken:
            def encode(self, *args):
                raise RuntimeError('model failure')
        with self.assertRaises(RuntimeError):
            build_index(self.root,self.index,Broken())
        self.assertEqual(self.index.read_bytes(),before)
    def test_latest_version_only(self):
        for version in [1,2]:
            p=self.root / f'v{version}';p.mkdir()
            (p/'normalized.json').write_text(json.dumps({'source_url':'https://x/page','source_base_url':'https://x/', 'page_id':'42','version':version,'markdown':f'Version {version}'}))
        docs=list(read_documents(self.root))
        self.assertEqual(len(docs),4)
        self.assertEqual([d['version'] for d in docs if d['source_url']=='https://x/page'],[2])

class CharacterTokenizer:
    def encode(self, text, add_special_tokens=False):
        return list(range(len(text))) + ([0,0] if add_special_tokens else [])
    def num_special_tokens_to_add(self, pair=False):
        return 4 if pair else 2
    def __call__(self, a, b, **kwargs):
        return {'input_ids': [0] * (len(a)+len(b)+4)}

class ModelWindowTests(UnitTestCase):
    def test_model_windows_cover_tail(self):
        text='x'*2000+'THE_END'
        parts=list(windows(text,CharacterTokenizer(),120))
        self.assertTrue(parts[-1].endswith('THE_END'))
        self.assertTrue(all(len(p)<=120 for p in parts))
    def test_embedding_windows_do_not_truncate(self):
        class Model:
            tokenizer=CharacterTokenizer()
            def encode(self, items, **kwargs):
                self.items=items
                return np.array([[1.,1.] for _ in items])
        embed=LocalEmbedder.__new__(LocalEmbedder)
        embed.model=Model();embed.budget=512
        vectors=embed.encode(['a'*1200+'END'])
        self.assertEqual(vectors.shape,(1,2))
        self.assertTrue(embed.model.items[-1].endswith('END'))
        self.assertTrue(all(s.startswith('passage: ') for s in embed.model.items))
    def test_reranker_checks_all_windows_and_keeps_max(self):
        class Model:
            tokenizer=CharacterTokenizer()
            def predict(self,pairs,**kwargs):
                self.pairs=pairs
                return [5 if b.endswith('END') else 0 for a,b in pairs]
        rank=LocalReranker.__new__(LocalReranker);rank.model=Model()
        self.assertEqual(rank.score('question',['a'*1200+'END']),[5.])
        self.assertGreater(len(rank.model.pairs),1)
        with self.assertRaises(RetrievalError):
            rank.score('q'*129,['text'])

@override_settings(ALLOWED_HOSTS=['testserver'])
class PanelTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('operator',password='test-only',is_staff=True)
        self.client.force_login(self.user)
    def test_panels_and_slash_commands(self):
        for url in ['/confluence','/search','/confluence/','/search/']:
            self.assertEqual(self.client.get(url).status_code,200)
        for cmd in ['/confluence','/search']:
            response=self.client.post('/command',{'command':cmd})
            self.assertEqual(response.status_code,302)
            self.assertEqual(response.url,cmd)
        self.assertEqual(self.client.post('/command',{'command':'/bad'}).status_code,400)
    def test_auth_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.get('/search').status_code,302)
        normal=get_user_model().objects.create_user('normal')
        self.client.force_login(normal)
        self.assertEqual(self.client.get('/search').status_code,403)
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/confluence',{'scope':'all'}).status_code,403)
    def test_queue_validation(self):
        self.client.post('/confluence',{'scope':'tree','target':'../bad'})
        self.assertFalse(ExportJob.objects.exists())
        self.client.post('/confluence',{'scope':'tree','target':'42'})
        self.assertEqual(ExportJob.objects.get().status,'queued')
    def test_missing_index_feedback(self):
        with override_settings(RAG_INDEX_PATH=Path('/not-present/test.sqlite3')):
            response=self.client.post('/search',{'query':'test','k':20,'limit':5})
        self.assertContains(response,'Henüz arama indeksi oluşturulmadı')
    def test_result_escaping_and_form_validation(self):
        self.assertContains(self.client.post('/search',{'query':'test','k':2,'limit':5}),'Sonuç sayısı K değerini aşamaz')
        with tempfile.NamedTemporaryFile() as file, override_settings(RAG_INDEX_PATH=Path(file.name)), patch('retrieval.views.embedder'),patch('retrieval.views.reranker'),patch('retrieval.views.search_index',return_value=[{'title':'<script>x</script>','text':'<img onerror=x>','vector_rank':1,'vector_score':1.,'rerank_score':2.,'token_count':5}]):
            response=self.client.post('/search',{'query':'test','k':2,'limit':1})
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>x</script>')
    def test_worker_processes_queued_job(self):
        job=ExportJob.objects.create(owner=self.user,scope='all')
        with patch('retrieval.management.commands.run_panel_worker.ConfluenceClient'),patch('retrieval.management.commands.run_panel_worker.crawl',return_value={'status':'completed','exported':2}):
            call_command('run_panel_worker',once=True)
        job.refresh_from_db()
        self.assertEqual(job.status,'completed')
