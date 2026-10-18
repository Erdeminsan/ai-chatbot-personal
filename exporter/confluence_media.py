"""Preserve storage-format image occurrences, captions and analysis together."""
import re
import uuid

from bs4 import Tag
from markdownify import markdownify


def md(node):
    return markdownify(str(node), heading_style='ATX', keep_inline_images_in=['p', 'td', 'th']).strip()


class ConfluenceMedia:
    def __init__(self, records, analyze=None):
        self.records = {record['title']: record for record in records}
        self.analyze = analyze
        self.groups, self.warnings, self.tokens = [], [], {}
        self.prefix = 'CFMEDIA' + uuid.uuid4().hex.upper()

    @staticmethod
    def unit(image):
        figures = image.find_parents('figure')
        if figures:
            return figures[-1]
        paragraph = image.find_parent('p')
        if paragraph:
            return paragraph
        return image

    @staticmethod
    def context(soup, unit, images):
        captions, related = [], []
        explicit = False
        for node in unit.find_all(['figcaption', 'ac:caption']):
            text = node.get_text(' ', strip=True)
            if text:
                captions.append({'method': node.name, 'text': text})
                explicit = True
        for image in images:
            # ac:title is a tooltip/title in Data Center, not always a visible caption.
            title = image.get('ac:title', '').strip()
            if title:
                captions.append({'method': 'ac:title', 'text': title})
                related.append({'method': 'ac:title', 'markdown': md(title)})
            refs = image.get('aria-describedby', image.get('ac:aria-describedby', ''))
            for ident in refs.split():
                target = soup.find(id=ident)
                if target is None or not target.get_text(' ', strip=True):
                    continue
                item = {'method': 'aria-describedby', 'text': target.get_text(' ', strip=True)}
                if item not in captions:
                    captions.append(item)
                    if target is not unit and unit not in target.parents:
                        related.append({'method': item['method'], 'markdown': md(target)})
                explicit = True
        # Inline prose is already part of the group and must reach the model too.
        if not explicit and unit.name == 'p':
            text = ' '.join(str(s).strip() for s in unit.find_all(string=True)
                            if not s.find_parent(['ac:image', 'ac:caption']))
            if text.strip():
                captions.append({'method': 'inline_text', 'text': text.strip()})
                explicit = True
        if not explicit:
            # Stay within the same cell/section: never cross a heading or another visual.
            for sibling in (unit.find_next_sibling(), unit.find_previous_sibling()):
                if not isinstance(sibling, Tag):
                    continue
                classes = ' '.join(sibling.get('class', []))
                is_caption = sibling.name == 'figcaption' or bool(re.search(r'(?:^|[\s_-])caption(?:$|[\s_-])', classes))
                if sibling.name != 'p' and not is_caption:
                    continue
                if sibling.find(['ac:image', 'img', 'svg', 'figure', 'h1', 'h2', 'h3', 'pre']):
                    continue
                text = sibling.get_text(' ', strip=True)
                if not text or len(text) > 1000:
                    continue
                method = 'adjacent_caption' if is_caption else 'adjacent_text_heuristic'
                captions.append({'method': method, 'text': text})
                related.append({'method': method, 'markdown': md(sibling)})
                break
        return captions, related

    def replace(self, soup, codes):
        def restore(text):
            for key, value in codes.items():
                text = text.replace(key, value)
            return text

        units, seen = [], set()
        for image in soup.find_all('ac:image'):
            unit = self.unit(image)
            if id(unit) not in seen:
                units.append(unit)
                seen.add(id(unit))
        for number, unit in enumerate(units, 1):
            if soup not in unit.parents:
                continue
            images = [unit] if unit.name == 'ac:image' else unit.find_all('ac:image')
            captions, related = self.context(soup, unit, images)
            captions = [{**caption, 'text': restore(caption['text'])} for caption in captions]
            group_id = f'media-group:{number}'
            assets, placeholders = [], {}
            context = restore('\n'.join(x['text'] for x in captions))
            for image in images:
                attachment = image.find('ri:attachment')
                filename = attachment.get('ri:filename') if attachment else None
                foreign = attachment is not None and attachment.find(['ri:page', 'ri:space']) is not None
                source = self.records.get(filename) if not foreign else None
                occurrence = f'media-{number}-{len(assets) + 1}'
                record = {**(source or {}), 'id': occurrence,
                          'attachment_id': source.get('id') if source else None,
                          'title': filename or 'harici görsel', 'path': source.get('path') if source else None,
                          'alt': image.get('ac:alt', filename or ''),
                          'image_title': image.get('ac:title', ''),
                          'reference_type': 'foreign_page' if foreign else ('attachment' if attachment else 'external_url')}
                external = image.find('ri:url')
                if external:
                    record['source_url'] = external.get('ri:value')
                if source:
                    source.setdefault('media_group_ids', [])
                    if group_id not in source['media_group_ids']:
                        source['media_group_ids'].append(group_id)
                    # This list belongs to the source attachment, not to an occurrence.
                    record.pop('media_group_ids', None)
                label = record['alt'] or record['title']
                label = re.sub(r'([\\\[\]])', r'\\\1', label).replace('\n', ' ')
                if record['path']:
                    markup = f'![{label}]({record["path"]})'
                    if self.analyze:
                        record['enrichment'], warnings = self.analyze(
                            source, '\n'.join([record['alt'], context]))
                        self.warnings.extend(f'{record["title"]}: {warning}' for warning in warnings)
                else:
                    markup = f'[Çözülemeyen görsel: {label}]'
                    self.warnings.append(f'Görsel çözülemedi: {filename or "harici görsel"}')
                key = self.prefix + 'IMAGE' + str(len(placeholders)) + 'GROUP' + str(number)
                placeholders[key] = markup
                holder = soup.new_tag('span')
                holder.string = key
                # Keep source captions inside the replacement instead of discarding them.
                for caption in list(image.find_all('ac:caption')):
                    holder.append(caption.extract())
                image.replace_with(holder)
                if image is unit:
                    unit = holder
                assets.append(record)
            for caption in unit.find_all('ac:caption'):
                caption.name = 'div'
            body = restore(md(unit))
            for key, markup in placeholders.items():
                body = body.replace(key, markup)
            lines = [f'<!-- {group_id} -->', body]
            for item in related:
                heading = {'adjacent_text_heuristic': 'Yakın bağlam (otomatik eşleştirme)',
                           'ac:title': 'Görsel başlık/ipuç metni'}.get(item['method'], 'İlişkili açıklama')
                lines.extend([f'**{heading}:**', restore(item['markdown'])])
            for record in assets:
                for kind, value in record.get('enrichment', {}).items():
                    heading = {'ocr': 'OCR metni', 'diagram': 'Diyagram kaynak yapısı',
                               'vision': 'Model yorumu — doğrulama gerekli'}[kind]
                    lines.extend([f'**{record["id"]} — {heading}:**',
                                  '\n'.join('> ' + line for line in value.get('text', '').splitlines())])
            lines.append(f'<!-- /{group_id} -->')
            block = '\n\n'.join(lines)
            self.groups.append({'id': group_id, 'captions': captions, 'assets': assets, 'markdown': block})
            key = self.prefix + 'GROUP' + str(number)
            self.tokens[key] = block
            holder = soup.new_tag('p')
            holder.string = key
            unit.replace_with(holder)
        return self.tokens
