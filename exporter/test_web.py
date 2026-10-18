import base64
import io
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

from exporter.client import ExportError
from exporter.enrichment import EnrichmentOptions
from exporter.web import export_web
from exporter.web_client import WebClient


def png_bytes():
    stream = io.BytesIO()
    Image.new('RGB', (20, 20), 'white').save(stream, 'PNG')
    return stream.getvalue()


class FixtureClient:
    def __init__(self, html):
        self.html = html.encode('utf-8')
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        if url == 'https://example.com/start':
            return self.html, 'https://example.com/docs/page', 'text/html; charset=utf-8'
        return png_bytes(), url, 'image/png'


class WebExportTests(TestCase):
    def run_export(self, html, **kwargs):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        client = FixtureClient('<meta charset="utf-8">' + html)
        target, warnings = export_web(client, 'https://example.com/start', temp.name, **kwargs)
        return client, target, json.loads((target / 'normalized.json').read_text()), warnings

    def test_figure_groups_two_images_and_caption_in_source_order(self):
        client, target, data, _ = self.run_export('''<title>İş akışı</title><nav>Menu</nav><main>
          <p>Önce</p><figure><img src="../a.png" alt="Akış"><img src="/b.png">
          <figcaption>İki adımlı <strong>işlem</strong>.</figcaption></figure><p>Sonra</p></main>''')
        text = (target / 'page.md').read_text()
        self.assertNotIn('Menu', text)
        self.assertLess(text.index('Önce'), text.index('<!-- media-group:1 -->'))
        self.assertLess(text.index('İki adımlı'), text.index('<!-- /media-group:1 -->'))
        self.assertLess(text.index('<!-- /media-group:1 -->'), text.index('Sonra'))
        self.assertEqual(len(data['media_groups']), 1)
        self.assertEqual(len(data['media_groups'][0]['assets']), 2)
        self.assertEqual(data['media_groups'][0]['captions'][0]['method'], 'figcaption')
        self.assertIn('https://example.com/a.png', client.calls)
        for record in data['media_groups'][0]['assets']:
            self.assertTrue((target / record['path']).is_file())
        self.assertEqual(data['title'], 'İş akışı')

    def test_adjacent_paragraph_is_context_not_certain_caption(self):
        _, _, data, _ = self.run_export('''<article><h2>Süreç</h2><div><a><img src="/a.png"></a></div>
          <p>İstemci önce sunucuya istek gönderir.</p><h2>Diğer bölüm</h2></article>''')
        group = data['media_groups'][0]
        self.assertEqual(group['captions'][0]['method'], 'adjacent_text_heuristic')
        self.assertIn('İstemci önce', group['markdown'])
        self.assertIn('Yakın bağlam (otomatik eşleştirme)', group['markdown'])
        self.assertNotIn('Diğer bölüm', group['markdown'])

    def test_aria_description_and_alt_preserved(self):
        _, _, data, _ = self.run_export('''<main><img src="/a.png" alt="A [B]" aria-describedby="explain">
          <h2>Başka bölüm</h2><p id="explain">Açık ilişki.</p></main>''')
        group = data['media_groups'][0]
        self.assertEqual(group['captions'][0]['method'], 'aria-describedby')
        self.assertIn('Açık ilişki.', group['markdown'])
        self.assertIn(r'A \[B\]', group['markdown'])

    def test_lazy_image_base_url_srcset_and_download_deduplication(self):
        client, _, data, _ = self.run_export('''<head><base href="https://cdn.example.org/media/"></head><main>
          <img src="placeholder.gif" data-src="real.png"><img src="real.png">
          <picture><source srcset="small.png 1x, large.png 2x"><img></picture>
          <a href="next">Sonraki</a></main>''')
        self.assertEqual(client.calls.count('https://cdn.example.org/media/real.png'), 1)
        self.assertIn('https://cdn.example.org/media/large.png', client.calls)
        self.assertIn('https://cdn.example.org/media/next', data['markdown'])

    def test_mermaid_sequence_plantuml_and_code_fences(self):
        _, _, data, _ = self.run_export('''<main><p>Önce</p><pre><code class="language-mermaid">sequenceDiagram
    A-&gt;&gt;B: Merhaba</code></pre><div class="mermaid">flowchart TD
    A--&gt;B</div><script type="text/plantuml">@startuml
A -&gt; B
@enduml</script><pre><code class="language-java">// ```
run();</code></pre><script>secret()</script><p>Sonra</p></main>''')
        text = data['markdown']
        self.assertIn('```mermaid\nsequenceDiagram\n    A->>B: Merhaba', text)
        self.assertIn('```plantuml', text)
        self.assertIn('````java\n// ```', text)
        self.assertNotIn('secret()', text)
        self.assertEqual(len(data['diagrams']), 3)
        self.assertNotIn('WEBEXPORT', text)

    def test_svg_labels_preserved_without_inventing_flow(self):
        _, target, data, warnings = self.run_export('''<main><figure><svg xmlns="http://www.w3.org/2000/svg">
          <title>Sequence</title><text>A</text><text>B</text></svg><figcaption>Giriş akışı.</figcaption></figure></main>''')
        record = data['media_groups'][0]['assets'][0]
        self.assertEqual(record['svg_text'], ['Sequence', 'A', 'B'])
        self.assertTrue((target / record['path']).exists())
        self.assertIn('Giriş akışı.', data['media_groups'][0]['markdown'])
        self.assertTrue(any('SVG' in w for w in warnings))

    def test_failed_image_retains_text_and_reports_warning(self):
        with patch.object(FixtureClient, 'fetch', autospec=True) as fetch:
            fetch.side_effect = [(b'<main><img src="/bad.png"><p>Explanation</p></main>',
                                  'https://example.com/page', 'text/html'), ExportError('HTTP 403')]
            _, _, data, warnings = self.run_export('unused')
        self.assertIn('Explanation', data['markdown'])
        self.assertIn('HTTP 403', data['media_groups'][0]['assets'][0]['error'])
        self.assertEqual(data['status'], 'needs_review')
        self.assertTrue(warnings)

    def test_inline_data_image(self):
        source = base64.b64encode(png_bytes()).decode('ascii')
        client, target, data, _ = self.run_export(f'<main><img src="data:image/png;base64,{source}"></main>')
        self.assertEqual(len(client.calls), 1)
        self.assertEqual((target / data['media_groups'][0]['assets'][0]['path']).read_bytes(), png_bytes())

    def test_code_inside_figure_resolves_in_json_group_too(self):
        _, _, data, _ = self.run_export('''<main><figure><img src="a.png">
          <pre><code class="mermaid">flowchart TD\n  A--&gt;B</code></pre>
          <figcaption>Flow source</figcaption></figure></main>''')
        group = data['media_groups'][0]['markdown']
        self.assertIn('```mermaid', group)
        self.assertNotIn('WEBEXPORT', group)
        self.assertEqual(len(data['diagrams']), 1)

    def test_extensionless_generic_cdn_image(self):
        with patch.object(FixtureClient, 'fetch', autospec=True) as fetch:
            fetch.side_effect = [(b'<main><img src="/download?id=3"></main>', 'https://example.com/page', 'text/html'),
                                 (png_bytes(), 'https://cdn.example.com/blob', 'application/octet-stream')]
            _, target, data, _ = self.run_export('unused')
        record = data['media_groups'][0]['assets'][0]
        self.assertTrue(record['path'].endswith('.png'))
        self.assertTrue((target / record['path']).exists())

    def test_selector_tables_lists_links_and_missing_selector(self):
        html = '''<main>Not selected</main><section id="content"><h2>Title</h2><ul><li>One</li></ul>
          <table><tr><th>Key</th><th>Value</th></tr><tr><td>a</td><td>b</td></tr></table>
          <a href="../next">Link</a></section>'''
        _, _, data, _ = self.run_export(html, selector='#content')
        self.assertNotIn('Not selected', data['markdown'])
        self.assertIn('| Key | Value |', data['markdown'])
        self.assertIn('https://example.com/next', data['markdown'])
        for selector in ('#missing', '['):
            with self.assertRaises(ExportError):
                self.run_export(html, selector=selector)

    def test_ocr_and_vision_stay_with_corresponding_media(self):
        result = {'ocr': {'text': 'OCR WORDS', 'generated': True},
                  'vision': {'text': 'MODEL FLOW', 'generated': True, 'requires_review': True}}
        with patch('exporter.web.enrich_attachment', return_value=(result, [])) as enrich:
            _, _, data, _ = self.run_export('<main><figure><img src="a.png"><figcaption>Caption</figcaption></figure></main>',
                                           options=EnrichmentOptions(ocr=True, vision=True))
        group = data['media_groups'][0]['markdown']
        self.assertIn('Caption', group)
        self.assertIn('OCR WORDS', group)
        self.assertIn('MODEL FLOW', group)
        self.assertTrue(data['generated_content_requires_review'])
        self.assertIn('Caption', enrich.call_args.kwargs['context'])

    @patch.dict(os.environ, {'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'OLLAMA_MODEL': 'fixture'})
    def test_vision_receives_caption_as_untrusted_context(self):
        import requests
        from exporter.enrichment import vision_describe
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"message":{"content":"Description"}}'
        with patch('requests.Session.post', return_value=response) as post:
            vision_describe(Image.new('RGB', (20, 20)), context='Caption from page')
        prompt = post.call_args.kwargs['json']['messages'][0]['content']
        self.assertIn('Caption from page', prompt)
        self.assertIn('<page_context>', prompt)

    def test_same_image_has_separate_context_for_each_occurrence(self):
        with patch('exporter.web.enrich_attachment', return_value=({}, [])) as enrich:
            client, _, data, _ = self.run_export('''<main>
              <figure><img src="same.png"><figcaption>First context</figcaption></figure>
              <figure><img src="same.png"><figcaption>Second context</figcaption></figure></main>''')
        self.assertEqual(client.calls.count('https://example.com/docs/same.png'), 1)
        self.assertEqual(enrich.call_count, 2)
        self.assertIn('First context', enrich.call_args_list[0].kwargs['context'])
        self.assertIn('Second context', enrich.call_args_list[1].kwargs['context'])

    def test_selector_can_be_figure_image_or_code_itself(self):
        html = '''<main><figure id="figure"><img id="image" src="a.png"><figcaption>Caption</figcaption></figure>
          <pre id="code"><code class="language-mermaid">graph TD\n  A--&gt;B</code></pre></main>'''
        for selector in ('#figure', '#image'):
            _, _, data, _ = self.run_export(html, selector=selector)
            self.assertEqual(len(data['media_groups']), 1)
            self.assertIn('<!-- media-group:1 -->', data['markdown'])
            self.assertNotIn('WEBEXPORT', data['markdown'])
        _, _, data, _ = self.run_export(html, selector='#code')
        self.assertIn('```mermaid', data['markdown'])

    def test_http_charset_preserves_turkish_without_meta_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            client = FixtureClient('')
            html = '<main><p>İşlem açıklaması: öğrenci.</p></main>'.encode('iso-8859-9')
            with patch.object(client, 'fetch', return_value=(html, 'https://example.com/page', 'text/html; charset=iso-8859-9')):
                target, _ = export_web(client, 'https://example.com/start', folder)
            self.assertIn('İşlem açıklaması: öğrenci.', (target / 'page.md').read_text())

    def test_html_only_and_no_partial_output(self):
        with tempfile.TemporaryDirectory() as folder:
            client = FixtureClient('')
            with patch.object(client, 'fetch', return_value=(b'%PDF', 'https://example.com/a.pdf', 'application/pdf')):
                with self.assertRaises(ExportError):
                    export_web(client, 'https://example.com/start', folder)
            with self.assertRaises(ExportError):
                export_web(FixtureClient('<main></main>'), 'https://example.com/start', folder)
            self.assertFalse(list(Path(folder).iterdir()))


class WebClientTests(TestCase):
    def test_no_confluence_token_and_redirect_scheme_validation(self):
        import requests
        with patch.dict(os.environ, {'CONFLUENCE_PAT': 'must-not-leak'}):
            client = WebClient()
        self.addCleanup(client.close)
        self.assertNotIn('Authorization', client.session.headers)
        response = requests.Response()
        response.status_code = 302
        response.headers['Location'] = 'file:///etc/passwd'
        response._content_consumed = True
        with patch.object(client.session, 'get', return_value=response):
            with self.assertRaises(ExportError):
                client.fetch('https://example.com')

    def test_size_limit_and_successful_redirect(self):
        import requests
        client = WebClient()
        self.addCleanup(client.close)
        def response(status, data=b'', location=None):
            r = requests.Response()
            r.status_code, r._content, r._content_consumed = status, data, True
            if location:
                r.headers['Location'] = location
            r.headers['Content-Type'] = 'text/html'
            return r
        with patch.object(client.session, 'get', return_value=response(200, b'123456')):
            with self.assertRaises(ExportError):
                client.fetch('https://example.com', limit=5)
        with patch.object(client.session, 'get', side_effect=[response(302, location='/new'), response(200, b'OK')]):
            self.assertEqual(client.fetch('https://example.com')[1], 'https://example.com/new')


class WebCommandIntegrationTests(TestCase):
    def test_real_http_command_without_pat_and_grouped_enrichment(self):
        from django.core.management import call_command
        from django.conf import settings
        if not settings.configured:
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
            import django
            django.setup()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/image.png':
                    data, mime = png_bytes(), 'image/png'
                else:
                    data = (b'<html><head><meta charset="utf-8"></head><body><main>'
                            b'<h2>Flow</h2><figure><img src="/image.png"><figcaption>Step caption</figcaption></figure>'
                            b'<pre><code class="language-mermaid">sequenceDiagram\n  A-&gt;&gt;B: Request</code></pre>'
                            b'</main></body></html>')
                    mime = 'text/html; charset=utf-8'
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'CONFLUENCE_PAT': ''}):
                output = io.StringIO()
                call_command('export_web', url=f'http://127.0.0.1:{server.server_port}/page', output=folder, stdout=output)
                targets = list(Path(folder).glob('*/page.md'))
                self.assertEqual(len(targets), 1)
                text = targets[0].read_text()
                self.assertIn('Step caption', text)
                self.assertIn('```mermaid', text)
                self.assertIn('<!-- media-group:1 -->', text)
                self.assertEqual(len(list((targets[0].parent / 'assets').iterdir())), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
