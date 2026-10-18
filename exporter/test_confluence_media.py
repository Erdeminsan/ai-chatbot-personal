import json
import tempfile
from unittest import TestCase
from unittest.mock import patch

from .client import ExportError
from .confluence_media import ConfluenceMedia
from .enrichment import EnrichmentOptions
from .parser import convert
from .service import export_page
from .test_bulk import FakeClient, XML


def image(name='a.png', attrs='', body=''):
    return f'<ac:image {attrs}><ri:attachment ri:filename="{name}"/>{body}</ac:image>'


class MediaParsingTests(TestCase):
    def parse(self, storage, analyze=None):
        records = [{'id': '9', 'title': 'a.png', 'path': 'assets/9_a.png'},
                   {'id': '10', 'title': 'b.png', 'path': 'assets/10_b.png'}]
        media = ConfluenceMedia(records, analyze)
        text, warnings, macros = convert(storage, {r['title']: r['path'] for r in records}, media=media)
        return text, media.groups, warnings

    def test_storage_caption_is_not_discarded(self):
        text, groups, _ = self.parse('<p>Before</p>' + image(body='<ac:caption><p>Caption <strong>bold</strong></p></ac:caption>') + '<p>After</p>')
        self.assertEqual(groups[0]['captions'], [{'method': 'ac:caption', 'text': 'Caption bold'}])
        self.assertIn('Caption **bold**', groups[0]['markdown'])
        self.assertLess(text.index('Before'), text.index('<!-- media-group:1 -->'))
        self.assertLess(text.index('<!-- /media-group:1 -->'), text.index('After'))
        self.assertEqual(text.count('Caption **bold**'), 1)
        self.assertNotIn('CFMEDIA', text)

    def test_data_center_title_alt_and_adjacent_paragraph(self):
        text, groups, _ = self.parse('<p>' + image(attrs='ac:title="Tooltip" ac:alt="Flow [A]"') + '</p><p>Step explanation</p>')
        methods = {c['method'] for c in groups[0]['captions']}
        self.assertEqual(methods, {'ac:title', 'adjacent_text_heuristic'})
        self.assertIn('Görsel başlık/ipuç metni', text)
        self.assertIn(r'Flow \[A\]', text)
        self.assertIn('Yakın bağlam (otomatik eşleştirme)', groups[0]['markdown'])

    def test_multiple_images_share_explicit_figure_caption(self):
        _, groups, _ = self.parse('<figure>' + image() + image('b.png') + '<figcaption>Pair</figcaption></figure>')
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]['assets']), 2)
        self.assertEqual(groups[0]['captions'][0]['method'], 'figcaption')
        self.assertIn('Pair', groups[0]['markdown'])

    def test_inline_description_with_nested_image(self):
        _, groups, _ = self.parse('<p><strong>' + image() + '</strong> Inline explanation</p>')
        self.assertEqual(groups[0]['captions'][0]['method'], 'inline_text')
        self.assertIn('Inline explanation', groups[0]['markdown'])

    def test_aria_description_does_not_use_unrelated_neighbor(self):
        _, groups, _ = self.parse('<p>' + image(attrs='aria-describedby="caption"') + '</p><p>Unrelated</p><p id="caption">Explicit</p>')
        self.assertEqual(groups[0]['captions'][0]['method'], 'aria-describedby')
        self.assertIn('Explicit', groups[0]['markdown'])
        self.assertNotIn('Unrelated', groups[0]['markdown'])

    def test_context_does_not_cross_heading_or_table_cell(self):
        for storage in ('<p>' + image() + '</p><h2>Next</h2><p>Wrong</p>',
                        '<table><tr><td>' + image() + '</td><td><p>Wrong</p></td></tr></table>'):
            _, groups, _ = self.parse(storage)
            self.assertEqual(groups[0]['captions'], [])
            self.assertNotIn('Wrong', groups[0]['markdown'])

    def test_foreign_image_does_not_match_same_local_filename(self):
        foreign = '<ac:image><ri:attachment ri:filename="a.png"><ri:page ri:content-title="Other"/></ri:attachment><ac:caption><p>Foreign caption</p></ac:caption></ac:image>'
        text, groups, warnings = self.parse(foreign)
        self.assertIsNone(groups[0]['assets'][0]['path'])
        self.assertIsNone(groups[0]['assets'][0]['attachment_id'])
        self.assertNotIn('assets/9_a.png', text)
        self.assertIn('Foreign caption', groups[0]['markdown'])
        self.assertTrue(warnings)

    def test_source_code_inside_group_has_no_unresolved_tokens(self):
        code = '<ac:structured-macro ac:name="mermaid"><ac:plain-text-body><![CDATA[graph TD\nA-->B]]></ac:plain-text-body></ac:structured-macro>'
        text, groups, _ = self.parse('<figure>' + image() + code + '<figcaption>Flow source</figcaption></figure>')
        self.assertIn('```mermaid\ngraph TD', groups[0]['markdown'])
        self.assertNotIn('CFEXPORTCODETOKEN', json.dumps(groups))
        self.assertIn('Flow source', text)

    def test_clickable_image_is_preserved(self):
        storage = '<p><ac:link><ri:page ri:content-title="Target"/><ac:link-body>' + image() + '</ac:link-body></ac:link></p><p>Caption</p>'
        text, groups, warnings = self.parse(storage)
        self.assertIn('assets/9_a.png', text)
        self.assertEqual(len(groups), 1)
        self.assertTrue(any('bağlantısı' in w for w in warnings))


class MediaExportTests(TestCase):
    class Client(FakeClient):
        def __init__(self, storage):
            self.storage, self.downloads = storage, []

        def json(self, link, **kwargs):
            data = super().json(link, **kwargs)
            data['title'] = 'Page title'
            data['body']['storage']['value'] = self.storage
            return data

        def items(self, link):
            return iter([{'id': '9', 'title': 'a.png', '_links': {'download': '/download/a'}},
                         {'id': '10', 'title': 'flow.drawio', '_links': {'download': '/download/flow'}}])

        def download(self, link, path):
            self.downloads.append(link)
            path.write_bytes(XML if link.endswith('/flow') else b'image-fixture')

    def test_repeated_image_has_separate_context_and_inline_analysis(self):
        client = self.Client(image(body='<ac:caption>First context</ac:caption>') + image(body='<ac:caption>Second context</ac:caption>'))
        def analyze(path, title, options, *, context=None):
            if title == 'flow.drawio':
                return {'diagram': {'text': 'UNREFERENCED GRAPH'}}, []
            return {'ocr': {'text': 'OCR WORDS'}, 'vision': {'text': context, 'generated': True, 'requires_review': True}}, []
        with tempfile.TemporaryDirectory() as folder, patch('exporter.service.enrich_attachment', side_effect=analyze) as enrich:
            target, _ = export_page(client, '42', folder, options=EnrichmentOptions(ocr=True, vision=True))
            data = json.loads((target / 'normalized.json').read_text())
            text = (target / 'page.md').read_text()
        self.assertEqual(data['schema_version'], 3)
        self.assertEqual(len(client.downloads), 2)
        self.assertEqual(enrich.call_count, 3)
        self.assertEqual(data['attachments'][0]['media_group_ids'], ['media-group:1', 'media-group:2'])
        self.assertNotIn('enrichment', data['attachments'][0])
        for group, expected in zip(data['media_groups'], ['First context', 'Second context']):
            self.assertIn(expected, group['assets'][0]['enrichment']['vision']['text'])
            self.assertIn('Page title', group['assets'][0]['enrichment']['vision']['text'])
            self.assertIn('OCR WORDS', group['markdown'])
        appendix = text.split('## Eklerden çıkarılan bilgiler')[1]
        self.assertIn('UNREFERENCED GRAPH', appendix)
        self.assertNotIn('OCR WORDS', appendix)
        self.assertTrue(data['generated_content_requires_review'])

    def test_failed_download_keeps_caption_and_reports_warning(self):
        class Broken(self.Client):
            def download(self, link, path):
                if link.endswith('/a'):
                    raise ExportError('HTTP 403')
                super().download(link, path)
        with tempfile.TemporaryDirectory() as folder:
            target, warnings = export_page(Broken(image(body='<ac:caption>Important caption</ac:caption>')), '42', folder)
            data = json.loads((target / 'normalized.json').read_text())
        self.assertIn('Important caption', data['media_groups'][0]['markdown'])
        self.assertEqual(data['status'], 'needs_review')
        self.assertIsNone(data['media_groups'][0]['assets'][0]['path'])
        self.assertTrue(warnings)

    def test_analysis_warning_stays_visible_and_other_content_survives(self):
        with tempfile.TemporaryDirectory() as folder, patch('exporter.service.enrich_attachment', return_value=({}, ['OCR failed'])):
            target, warnings = export_page(self.Client('<p>Body</p>' + image()), '42', folder)
            data = json.loads((target / 'normalized.json').read_text())
        self.assertIn('Body', data['markdown'])
        self.assertTrue(any('OCR failed' in x for x in warnings))
        self.assertEqual(data['status'], 'needs_review')

    def test_resume_rejects_v2_output_instead_of_silently_skipping_grouping(self):
        with tempfile.TemporaryDirectory() as folder:
            target, _ = export_page(FakeClient(), '42', folder)
            data = json.loads((target / 'normalized.json').read_text())
            data['schema_version'] = 2
            (target / 'normalized.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ExportError, 'eski şemada'):
                export_page(FakeClient(), '42', folder, resume=True)

    def test_tree_export_uses_grouping_for_every_page(self):
        from pathlib import Path
        from .crawler import crawl
        class TreeClient(self.Client):
            def items(self, link):
                if '/child/attachment?' in link:
                    return super().items(link)
                return FakeClient.items(self, link)
        with tempfile.TemporaryDirectory() as folder:
            result = crawl(TreeClient('<p>' + image() + '</p><p>Tree caption</p>'), folder,
                           root_page_id='1', progress=lambda _: None)
            self.assertEqual(result['exported'], 4)
            for path in Path(folder).glob('*/*/normalized.json'):
                data = json.loads(path.read_text())
                self.assertEqual(data['schema_version'], 3)
                self.assertIn('Tree caption', data['media_groups'][0]['markdown'])
