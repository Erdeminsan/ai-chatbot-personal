import copy
import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from exporter.client import ConfluenceClient, ExportError
from exporter.parser import convert
from exporter.service import export_page

STORAGE = '''<h2>Örnek</h2><ac:structured-macro ac:name="code"><ac:parameter ac:name="language">java</ac:parameter><ac:plain-text-body><![CDATA[if (a < b) {
    run(); // ```
}]]></ac:plain-text-body></ac:structured-macro><ac:image><ri:attachment ri:filename="a.png"/></ac:image><ac:structured-macro ac:name="drawio"/>'''

class ExportTests(TestCase):
    def test_code_image_and_unknown_macro(self):
        text, warnings, macros = convert(STORAGE, {"a.png": "assets/1_a.png"})
        self.assertIn('````java\nif (a < b) {\n    run(); // ```\n}', text)
        self.assertIn('assets/1_a.png', text)
        self.assertIn('drawio', macros)
        self.assertTrue(any('drawio' in x for x in warnings))

    @patch.dict(os.environ, {"CONFLUENCE_BASE_URL": "https://example.com/confluence", "CONFLUENCE_PAT": "test"})
    def test_context_and_cross_origin(self):
        client = ConfluenceClient()
        self.addCleanup(client.session.close)
        for path in ('/rest/api/content', '/confluence/rest/api/content', 'rest/api/content'):
            self.assertEqual(client.resolve(path), 'https://example.com/confluence/rest/api/content')
        with self.assertRaises(ExportError):
            client.resolve('https://other.example/download')

    def test_export_and_duplicate_protection(self):
        class FakeClient:
            def json(self, *args, **kwargs):
                return copy.deepcopy({'id': '42', 'type': 'page', 'title': 'Örnek', 'version': {'number': 1}, 'body': {'storage': {'value': STORAGE}}})
            def items(self, link):
                return iter([{'id': '9', 'title': 'a.png', '_links': {'download': '/download/a.png'}}])
            def download(self, link, target):
                target.write_bytes(b'fake-fixture-image')
            def resolve(self, link):
                return 'https://example.com/' + link
        with tempfile.TemporaryDirectory() as directory:
            target, issues = export_page(FakeClient(), '42', directory)
            data = json.loads((target / 'normalized.json').read_text())
            self.assertEqual(data['page_id'], '42')
            self.assertEqual(data['status'], 'needs_review')
            self.assertTrue((target / data['attachments'][0]['path']).exists())
            self.assertTrue((target / 'raw.json').exists())
            with self.assertRaises(ExportError):
                export_page(FakeClient(), '42', directory)

    def test_foreign_attachment_not_matched_by_filename(self):
        text, warnings, _ = convert('<ac:image><ri:attachment ri:filename="a.png"><ri:page ri:content-title="Other"/></ri:attachment></ac:image>', {'a.png': 'assets/local.png'})
        self.assertNotIn('assets/local.png', text)
        self.assertTrue(warnings)

@patch.dict(os.environ, {"CONFLUENCE_BASE_URL": "https://example.com/confluence", "CONFLUENCE_PAT": "fixture-token"})
class SDKClientTests(TestCase):
    def client(self):
        client = ConfluenceClient()
        self.addCleanup(client.session.close)
        return client

    @staticmethod
    def response(status=200, payload=b'{"id":"42"}'):
        import requests
        response = requests.Response()
        response.status_code = status
        response._content = payload
        response._content_consumed = True
        response.url = 'https://example.com/confluence/rest/api/content/42'
        return response

    def test_sdk_request_and_pat_configuration(self):
        client = self.client()
        self.assertEqual(client.session.headers['Authorization'], 'Bearer fixture-token')
        self.assertFalse(client.api.cloud)
        with patch.object(client.session, 'request', return_value=self.response()) as request:
            self.assertEqual(client.json('rest/api/content/42', params={'expand': 'body.storage'})['id'], '42')
        args = request.call_args.kwargs
        self.assertEqual(args['url'], 'https://example.com/confluence/rest/api/content/42?expand=body.storage')
        self.assertFalse(args['allow_redirects'])
        self.assertTrue(args['verify'])

    def test_redirect_and_non_json(self):
        client = self.client()
        for response in (self.response(302), self.response(200, b'<html>SSO</html>'), self.response(403)):
            with patch.object(client.session, 'request', return_value=response):
                with self.assertRaises(ExportError):
                    client.json('rest/api/content/42')

    def test_sdk_pagination_context(self):
        client = self.client()
        pages = [self.response(payload=b'{"results":[{"id":"1"}],"_links":{"next":"/confluence/rest/api/content?start=1"}}'),
                 self.response(payload=b'{"results":[{"id":"2"}],"_links":{}}')]
        with patch.object(client.session, 'request', side_effect=pages) as request:
            self.assertEqual([x['id'] for x in client.items('rest/api/content')], ['1', '2'])
        self.assertEqual(request.call_args.kwargs['url'], 'https://example.com/confluence/rest/api/content?start=1')

    def test_binary_stream_uses_shared_session(self):
        client = self.client()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image.png'
            with patch.object(client.session, 'request', return_value=self.response(payload=b'\x89PNG\x00\xff')) as request:
                client.download('/download/attachments/42/image.png', path)
            self.assertEqual(path.read_bytes(), b'\x89PNG\x00\xff')
            self.assertTrue(request.call_args.kwargs['stream'])
