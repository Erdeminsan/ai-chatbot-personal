"""HTML -> Markdown with in-place media/context groups and provenance.

This is a single-document exporter, not a browser or a recursive crawler.
"""
import base64
import hashlib
import io
import mimetypes
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote_to_bytes, urlsplit

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify
from PIL import Image
from soupsieve import SelectorSyntaxError

from .client import ExportError
from .enrichment import EnrichmentOptions, RASTER, enrich_attachment
from .service import dump
from .web_client import web_url


def md(html):
    return markdownify(str(html), heading_style='ATX', keep_inline_images_in=['td', 'th', 'p']).strip()


def fence(text, language=''):
    marker = '`' * max(3, 1 + max([len(x) for x in re.findall(r'`+', text)] or [0]))
    return f'{marker}{language}\n{text.rstrip()}\n{marker}'


def diagram_language(node):
    classes = ' '.join(node.get('class', []))
    if node.name == 'pre' and node.code:
        classes += ' ' + ' '.join(node.code.get('class', []))
    match = re.search(r'(?:language-|lang-)([a-zA-Z0-9_+.-]+)', classes)
    if match:
        return match.group(1)
    for name in ('mermaid', 'plantuml', 'sequence', 'graphviz'):
        if name in classes.split() or node.get('type') == f'text/{name}':
            return name
    return ''


def image_source(node):
    # Prefer lazy-load originals over placeholder src values.
    for attr in ('data-src', 'data-original', 'data-lazy-src'):
        if node.get(attr):
            return node[attr]
    srcset = node.get('data-srcset') or node.get('srcset')
    if not srcset and node.parent.name == 'picture':
        source = node.parent.find('source', srcset=True)
        srcset = source.get('srcset') if source else None
    if srcset:
        # Data URLs contain commas; use src instead for that uncommon srcset form.
        if not srcset.lstrip().startswith('data:'):
            return srcset.split(',')[-1].strip().split()[0]
    return node.get('src', '')


class WebConverter:
    def __init__(self, client, html, url, folder, options, selector=None, encoding=None):
        self.client, self.url, self.folder, self.options = client, url, folder, options
        self.soup = BeautifulSoup(html, 'html.parser', from_encoding=encoding)
        self.title = self.soup.title.get_text(' ', strip=True) if self.soup.title else url
        self.base = url
        if self.soup.find('base', href=True):
            self.base = web_url(self.soup.find('base', href=True)['href'], url)
        try:
            self.root = self.soup.select_one(selector) if selector else (
                self.soup.find('main') or self.soup.find('article') or self.soup.body or self.soup)
        except SelectorSyntaxError:
            raise ExportError('Geçersiz --selector CSS ifadesi.') from None
        if self.root is None:
            raise ExportError('--selector ile eşleşen içerik bulunamadı.')
        # The selected node can itself be an image, figure or code block.
        # A stable wrapper lets all conversions replace that node in place.
        if self.root is not self.soup:
            self.root = self.root.wrap(self.soup.new_tag('div'))
        self.warnings, self.media_groups, self.diagrams = [], [], []
        self.tokens, self.downloads = {}, {}
        self.prefix = 'WEBEXPORT' + uuid.uuid4().hex.upper()

    def replace(self, node, value):
        token = self.prefix + str(len(self.tokens)) + 'END'
        self.tokens[token] = value
        holder = self.soup.new_tag('p')
        holder.string = token
        node.replace_with(holder)

    def restore(self, text):
        for key, value in reversed(list(self.tokens.items())):
            text = text.replace(key, value)
        return text

    def clean(self):
        for node in list(self.root.select('nav, footer, aside, form, style, template, noscript, [hidden], [aria-hidden="true"]')):
            if node.parent is not None:
                node.decompose()
        # Preserve source DSL before dropping executable scripts.
        for node in list(self.root.select('pre, .mermaid, .plantuml, .sequence, .graphviz, .language-mermaid, .language-plantuml, .language-dot, script[type^="text/"]')):
            if self.root not in node.parents:
                continue
            language = diagram_language(node)
            if node.name != 'pre' and not language:
                continue
            text = node.get_text() if node.name != 'script' else (node.string or '')
            block = fence(text, language)
            if language in {'mermaid', 'plantuml', 'sequence', 'graphviz', 'dot'}:
                self.diagrams.append({'language': language, 'source': text, 'generated': False})
                block += '\n\n> Diyagram kaynağı korundu; akış semantik olarak yorumlanmadı.'
            self.replace(node, block)
        for node in list(self.root.find_all('script')):
            node.decompose()
        for node in self.root.find_all('a', href=True):
            href = node['href']
            if href.startswith(('#', 'mailto:', 'tel:')):
                continue
            try:
                node['href'] = web_url(href, self.base)
            except ExportError:
                del node['href']
        for node in self.root.find_all(['canvas', 'iframe', 'object', 'embed']):
            self.warnings.append(f'{node.name}: gömülü/dinamik içerik işlenmedi.')

    def asset(self, node):
        record = {'kind': 'svg' if node.name == 'svg' else 'image',
                  'alt': node.get('alt', ''), 'source_url': None, 'path': None}
        try:
            if node.name == 'svg':
                data, content_type = str(node).encode('utf-8'), 'image/svg+xml'
                # Text extraction only: visible edge directions cannot be inferred from labels.
                record['svg_text'] = list(dict.fromkeys(
                    x.get_text(' ', strip=True) for x in node.find_all(['title', 'desc', 'text'])
                    if x.get_text(' ', strip=True)))
                record['interpretation'] = 'labels_only_no_flow_inference'
                self.warnings.append('SVG etiketleri korundu; ok yönleri ve diyagram akışı yorumlanmadı.')
            else:
                src = image_source(node)
                if not src:
                    raise ExportError('Görsel adresi bulunamadı.')
                if src.startswith('data:'):
                    if len(src) > 28 * 1024 * 1024:
                        raise ExportError('Gömülü görsel boyut sınırını aşıyor.')
                    header, payload = src.split(',', 1)
                    content_type = header[5:].split(';')[0]
                    data = base64.b64decode(payload, validate=True) if ';base64' in header else unquote_to_bytes(payload)
                else:
                    src = web_url(src, self.base)
                    record['source_url'] = src
                    if src in self.downloads:
                        return {**self.downloads[src], 'alt': record['alt']}
                    data, final_url, content_type = self.client.fetch(src, limit=20 * 1024 * 1024)
                    record['resolved_url'] = final_url
            mime = content_type.split(';')[0].strip().lower()
            suffix = mimetypes.guess_extension(mime) or Path(urlsplit(record['source_url'] or '').path).suffix.lower()
            if suffix == '.jpe':
                suffix = '.jpg'
            if suffix not in RASTER | {'.svg', '.drawio'}:
                suffix = Path(urlsplit(record['source_url'] or '').path).suffix.lower()
            if suffix not in RASTER | {'.svg', '.drawio'} and mime in {'', 'application/octet-stream'}:
                try:
                    with Image.open(io.BytesIO(data)) as image:
                        suffix = '.' + image.format.lower()
                except (OSError, ValueError):
                    pass
            if suffix not in RASTER | {'.svg', '.drawio'}:
                raise ExportError(f'Desteklenmeyen görsel biçimi: {mime or suffix}')
            if mime and not mime.startswith('image/') and mime not in {'application/octet-stream', 'application/xml', 'text/xml'}:
                raise ExportError(f'Görsel yerine farklı içerik geldi: {mime}')
            digest = hashlib.sha256(data).hexdigest()
            path = 'assets/' + digest[:24] + suffix
            (self.folder / path).write_bytes(data)
            record.update(path=path, sha256=digest, content_type=mime)
            if suffix == '.svg' and node.name != 'svg':
                svg = BeautifulSoup(data, 'html.parser')
                record['svg_text'] = list(dict.fromkeys(x.get_text(' ', strip=True) for x in svg.find_all(['title', 'desc', 'text'])))
                record['interpretation'] = 'labels_only_no_flow_inference'
                self.warnings.append('SVG etiketleri korundu; ok yönleri ve diyagram akışı yorumlanmadı.')
            if suffix in RASTER and not self.options.vision:
                self.warnings.append('Raster görsel korundu; anlamsal görsel/akış yorumu için --vision gerekir.')
            if record['source_url']:
                self.downloads[record['source_url']] = record.copy()
        except (ExportError, ValueError) as exc:
            record['error'] = str(exc)
            self.warnings.append(f'Görsel işlenemedi: {exc}')
        return record

    def media_unit(self, node):
        figure = node.find_parent('figure')
        if figure and (figure is self.root or self.root in figure.parents):
            return figure
        unit = node
        while unit.parent is not self.root and isinstance(unit.parent, Tag) and unit.parent.name in {'a', 'picture', 'p'}:
            unit = unit.parent
        return unit

    def context(self, unit, visuals):
        """Prefer explicit HTML associations; label adjacency as heuristic."""
        captions, related = [], []
        for node in unit.find_all('figcaption'):
            captions.append({'method': 'figcaption', 'text': node.get_text(' ', strip=True)})
        for visual in visuals:
            for ident in visual.get('aria-describedby', '').split():
                target = self.soup.find(id=ident)
                if target:
                    item = {'method': 'aria-describedby', 'text': target.get_text(' ', strip=True)}
                    if item not in captions:
                        captions.append(item)
                    if target is not unit and unit not in target.parents:
                        related.append({'method': item['method'], 'markdown': md(target)})
        if captions:
            return captions, related
        # Unwrap image-only layout containers to find a directly adjacent paragraph.
        anchor = unit
        while anchor.parent is not self.root and anchor.parent and anchor.parent.name in {'div', 'a', 'picture', 'p'}:
            if anchor.parent.get_text(' ', strip=True) or len(anchor.parent.find_all(['img', 'svg'])) != len(visuals):
                break
            anchor = anchor.parent
        for sibling in (anchor.find_next_sibling(), anchor.find_previous_sibling()):
            if sibling is None or sibling.name not in {'p', 'figcaption', 'div', 'span'}:
                continue
            classes = ' '.join(sibling.get('class', []))
            explicit = sibling.name == 'figcaption' or bool(re.search(r'(?:^|[\s_-])caption(?:$|[\s_-])', classes))
            if sibling.name != 'p' and not explicit:
                continue
            text = sibling.get_text(' ', strip=True)
            if not text or len(text) > 1000 or sibling.find(['img', 'svg', 'h1', 'h2', 'h3', 'pre', 'figure']):
                continue
            method = 'adjacent_caption' if explicit else 'adjacent_text_heuristic'
            captions.append({'method': method, 'text': text})
            related.append({'method': method, 'markdown': md(sibling)})
            # Keep source prose in its original location; the grouped copy makes
            # media context available to downstream chunking without losing prose.
            break
        return captions, related

    def convert(self):
        self.clean()
        units, seen = [], set()
        for node in self.root.find_all(['img', 'svg']):
            if node.name == 'svg' and node.find_parent('svg'):
                continue
            unit = self.media_unit(node)
            if id(unit) not in seen:
                seen.add(id(unit))
                units.append(unit)
        for index, unit in enumerate(units, 1):
            if self.root not in unit.parents:
                continue
            visuals = [unit] if unit.name in {'img', 'svg'} else unit.find_all(['img', 'svg'])
            visuals = [x for x in visuals if not x.find_parent('svg')]
            captions, related = self.context(unit, visuals)
            records = []
            for visual in visuals:
                record = self.asset(visual)
                record['id'] = f'media-{index}-{len(records) + 1}'
                if record['path']:
                    # Downloads are shared, interpretations belong to each occurrence:
                    # the same image can have different captions in different sections.
                    context = self.restore('\n'.join([record['alt']] + [x['text'] for x in captions] + [unit.get_text(' ', strip=True)]))
                    record['enrichment'], issues = enrich_attachment(
                        self.folder / record['path'], Path(record['path']).name, self.options, context=context)
                    self.warnings.extend(issues)
                records.append(record)
                label = record['alt'] or f'Görsel {index}.{len(records)}'
                # Escape Markdown syntax in alt labels; asset paths are generated.
                label = re.sub(r'([\\\[\]])', r'\\\1', label).replace('\n', ' ')
                markup = f'![{label}]({record["path"]})' if record['path'] else f'[İndirilemeyen görsel: {label}]'
                if not record['path'] and record.get('source_url'):
                    markup += '\n\nKaynak görsel: <' + record['source_url'] + '>'
                holder = self.soup.new_tag('span')
                key = self.prefix + 'IMAGE' + record['id'].replace('-', '')
                holder.string = key
                visual.replace_with(holder)
                record['_placeholder'] = key
                record['_markup'] = markup
                # If the unit is the image itself, use the replacement node below.
                if visual is unit:
                    unit = holder
            body = md(unit)
            for record in records:
                body = body.replace(record.pop('_placeholder'), record.pop('_markup'))
            body = self.restore(body)
            lines = [f'<!-- media-group:{index} -->', body]
            for item in related:
                heading = 'Yakın bağlam (otomatik eşleştirme)' if item['method'] == 'adjacent_text_heuristic' else 'İlişkili açıklama'
                lines += [f'**{heading}:**', item['markdown']]
            for record in records:
                if record.get('svg_text'):
                    lines += ['**SVG içindeki etiketler (akış yorumu değildir):**', '\n'.join(record['svg_text'])]
                for kind, value in record.get('enrichment', {}).items():
                    heading = {'ocr': 'OCR metni', 'diagram': 'Diyagram kaynak yapısı',
                               'vision': 'Model yorumu — doğrulama gerekli'}[kind]
                    lines += [f'**{record["id"]} — {heading}:**', '\n'.join('> ' + x for x in value.get('text', '').splitlines())]
            lines.append(f'<!-- /media-group:{index} -->')
            self.media_groups.append({'id': f'media-group:{index}', 'captions': captions,
                                      'assets': records, 'markdown': '\n\n'.join(lines)})
            self.replace(unit, self.media_groups[-1]['markdown'])
        markdown = md(self.root)
        # A code token may be nested inside a figure/media token.
        markdown = self.restore(markdown)
        if not markdown.strip():
            raise ExportError('Sayfada aktarılabilir içerik bulunamadı; JavaScript veya giriş gerekebilir.')
        self.warnings = list(dict.fromkeys(self.warnings))
        return markdown + '\n'


def export_web(client, url, output, *, selector=None, options=None):
    options = options or EnrichmentOptions()
    requested_url = web_url(url)
    html, final_url, content_type = client.fetch(requested_url)
    mime = content_type.split(';')[0].strip().lower()
    if mime not in {'text/html', 'application/xhtml+xml'}:
        raise ExportError('URL bir HTML sayfası döndürmeli; doğrudan dosya URL’si desteklenmiyor.')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.web-', dir=output))
    try:
        (stage / 'assets').mkdir()
        (stage / 'raw.html').write_bytes(html)
        charset = re.search(r'charset\s*=\s*[\"\x27]?([^;\s\"\x27]+)', content_type, re.I)
        converter = WebConverter(client, html, final_url, stage, options, selector,
                                 encoding=charset.group(1) if charset else None)
        markdown = converter.convert()
        exported_at = datetime.now(timezone.utc)
        data = {'schema_version': 1, 'source_type': 'web', 'requested_url': requested_url,
                'source_url': final_url, 'title': converter.title, 'exported_at': exported_at.isoformat(),
                'selector': selector, 'markdown': markdown, 'media_groups': converter.media_groups,
                'diagrams': converter.diagrams, 'warnings': converter.warnings,
                'enrichment_options': options.metadata(),
                'generated_content_requires_review': any(
                    a.get('enrichment', {}).get('vision') for g in converter.media_groups for a in g['assets']),
                'status': 'needs_review' if converter.warnings else 'converted',
                'limitations': ['single_page', 'no_javascript_execution', 'no_login', 'no_acl',
                                'adjacent_text_is_heuristic', 'no_svg_flow_interpretation']}
        dump(stage / 'normalized.json', data)
        (stage / 'page.md').write_text('# ' + converter.title.replace('\n', ' ') + '\n\nKaynak: ' + final_url + '\n\n' + markdown, encoding='utf-8')
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', urlsplit(final_url).hostname or 'web')[:60]
        destination = output / (slug + '_' + exported_at.strftime('%Y%m%dT%H%M%S%fZ') + '_' + uuid.uuid4().hex[:6])
        stage.rename(destination)
        return destination, converter.warnings
    finally:
        if stage.exists():
            shutil.rmtree(stage)
