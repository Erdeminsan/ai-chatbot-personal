import base64
import copy
import json
import os
import tempfile
import zlib
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import quote, urlsplit, parse_qs
from PIL import Image, ImageDraw, ImageFont
from exporter.client import ExportError
from exporter.crawler import crawl
from exporter.enrichment import EnrichmentOptions, drawio_graph, enrich_attachment, vision_describe, vision_url

XML = b'<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="a" vertex="1" value="Start"/><object id="b" label="Finish"><mxCell vertex="1"/></object><mxCell id="e" edge="1" source="a" target="b" value="yes" style="endArrow=classic;"/></root></mxGraphModel>'

class FakeClient:
    def items(self, link):
        if link.startswith('rest/api/space?'):
            return iter([{'key': 'A'}, {'key': 'B'}])
        if '/child/attachment?' in link:
            return iter([])
        if '/child/page?' in link:
            ident = link.split('/')[3]
            return iter([{'id': i} for i in {'1': ['2', '3'], '2': ['4'], '3': ['4'], '4': []}[ident]])
        key = parse_qs(urlsplit(link).query)['spaceKey'][0]
        return iter([{'id': i} for i in {'A': ['1', '2'], 'B': ['3', '4']}[key]])
    def json(self, link, **kwargs):
        ident = link.split('/')[-1]
        return {'id': ident, 'type': 'page', 'title': 'Page ' + ident,
                'space': {'key': 'A'}, 'version': {'number': 1},
                'ancestors': [], 'body': {'storage': {'value': '<p>Hello</p>'}}}
    def resolve(self, link):
        return 'https://example.com/' + link

class BulkTests(TestCase):
    def test_all_spaces_exports_and_resumes(self):
        with tempfile.TemporaryDirectory() as folder:
            result = crawl(FakeClient(), folder, all_spaces=True, progress=lambda _: None)
            self.assertEqual(result['exported'], 4)
            self.assertEqual(result['status'], 'completed')
            result = crawl(FakeClient(), folder, all_spaces=True, resume=True, progress=lambda _: None)
            self.assertEqual(result['reused'], 4)
            self.assertEqual(result['exported'], 0)

    def test_tree_traverses_grandchildren_once(self):
        with tempfile.TemporaryDirectory() as folder:
            result = crawl(FakeClient(), folder, root_page_id='1', progress=lambda _: None)
            self.assertEqual(result['exported'], 4)

    def test_failed_page_does_not_stop_other_pages(self):
        class BrokenClient(FakeClient):
            def json(self, link, **kwargs):
                if link.endswith('/2'):
                    raise ExportError('HTTP 403')
                return super().json(link, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            result = crawl(BrokenClient(), folder, all_spaces=True, progress=lambda _: None)
            self.assertEqual(result['exported'], 3)
            self.assertEqual(result['failed'], 1)
            self.assertEqual(result['status'], 'partial')

    def test_enumeration_error_reported(self):
        class BrokenClient(FakeClient):
            def items(self, link):
                if 'spaceKey=B' in link:
                    raise ExportError('HTTP 403')
                return super().items(link)
        with tempfile.TemporaryDirectory() as folder:
            result = crawl(BrokenClient(), folder, all_spaces=True, progress=lambda _: None)
            self.assertEqual(result['enumeration_errors'], 1)
            self.assertEqual(result['status'], 'partial')

class EnrichmentTests(TestCase):
    def test_drawio_uncompressed_wrapped_nodes(self):
        graph = drawio_graph(XML)
        self.assertEqual(graph['pages'][0]['nodes'][1]['id'], 'b')
        self.assertEqual(graph['pages'][0]['edges'][0]['end_arrow'], 'classic')

    def test_drawio_compressed_multiple_pages(self):
        compressor = zlib.compressobj(wbits=-15)
        packed = compressor.compress(quote(XML.decode()).encode()) + compressor.flush()
        data = b'<mxfile><diagram id="1">' + base64.b64encode(packed) + b'</diagram><diagram id="2">' + XML + b'</diagram></mxfile>'
        self.assertEqual(len(drawio_graph(data)['pages']), 2)

    def test_reject_xml_entities(self):
        with self.assertRaises(Exception):
            drawio_graph(b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><mxGraphModel>&y;</mxGraphModel>')

    def test_real_tesseract_english(self):
        options = EnrichmentOptions(ocr=True, ocr_lang='eng')
        options.validate()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.png'
            image = Image.new('RGB', (900, 160), 'white')
            font = ImageFont.load_default(size=48)
            ImageDraw.Draw(image).text((25, 45), 'CONFLUENCE EXPORT 123', fill='black', font=font)
            image.save(path)
            result, warnings = enrich_attachment(path, 'test.png', options)
            self.assertFalse(warnings)
            self.assertIn('CONFLUENCE', result['ocr']['text'])
            self.assertGreater(len(result['ocr']['words']), 0)

    @patch.dict(os.environ, {'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'OLLAMA_MODEL': 'fixture-model'})
    def test_vision_payload_and_separate_session(self):
        import requests
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"message":{"content":"Start to finish"}}'
        with patch('requests.Session.post', return_value=response) as post:
            text = vision_describe(Image.new('RGB', (20, 20)))
        self.assertEqual(text, 'Start to finish')
        payload = post.call_args.kwargs['json']
        self.assertTrue(payload['messages'][0]['images'])
        self.assertFalse(payload['stream'])
        self.assertNotIn('headers', post.call_args.kwargs)

    @patch.dict(os.environ, {'OLLAMA_BASE_URL': 'https://external.example.com'})
    def test_vision_external_endpoint_rejected(self):
        with self.assertRaises(ExportError):
            vision_url()

class EndToEndEnrichmentTests(TestCase):
    def test_export_attached_drawio_graph_to_json_and_markdown(self):
        from exporter.service import export_page
        class DiagramClient(FakeClient):
            def items(self, link):
                return iter([{'id': '99', 'title': 'flow.drawio', '_links': {'download': '/download/flow'}}])
            def download(self, link, path):
                path.write_bytes(XML)
        with tempfile.TemporaryDirectory() as folder:
            target, warnings = export_page(DiagramClient(), '42', folder)
            normalized = json.loads((target / 'normalized.json').read_text())
            self.assertEqual(normalized['attachments'][0]['enrichment']['diagram']['pages'][0]['edges'][0]['target'], 'b')
            self.assertIn('Düğüm a: Start', (target / 'page.md').read_text())
