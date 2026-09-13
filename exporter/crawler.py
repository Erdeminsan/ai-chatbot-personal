"""Sequential, paginated inventory with an append-only run report."""
import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from .client import ExportError
from .service import export_page, dump


def crawl(client, output, *, all_spaces=False, space_key=None, root_page_id=None,
          include_archived_spaces=False, resume=False, options=None, progress=print):
    if sum([bool(all_spaces), bool(space_key), bool(root_page_id)]) != 1:
        raise ExportError("Bir kapsam seçin: --all-spaces, --space-key veya --root-page-id.")
    if root_page_id and not re.fullmatch(r"[0-9]+", root_page_id):
        raise ExportError("Sayfa ID yalnızca rakamlardan oluşmalı.")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report = output / f'run-{stamp}.jsonl'
    summary = {'scope': {'all_spaces': all_spaces, 'space_key': space_key, 'root_page_id': root_page_id},
               'exported': 0, 'reused': 0, 'needs_review': 0, 'failed': 0, 'enumeration_errors': 0,
               'report': report.name, 'started_at': stamp, 'status': 'running', 'spaces': []}
    seen = set()

    def log(event):
        with report.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')

    def failure(scope, exc):
        summary['enumeration_errors'] += 1
        log({'event': 'enumeration_error', 'scope': scope, 'error': str(exc)})
        progress(f'Listeleme hatası: {scope}')

    def collect(page_id):
        page_id = str(page_id)
        if page_id in seen:
            return
        seen.add(page_id)
        try:
            target, issues = export_page(client, page_id, output, options=options, resume=resume)
            reused = 'existing_version_reused' in issues
            actual_issues = [x for x in issues if x != 'existing_version_reused']
            summary['reused' if reused else 'exported'] += 1
            if actual_issues:
                summary['needs_review'] += 1
            log({'event': 'page', 'id': page_id, 'path': str(target.relative_to(output)),
                 'reused': reused, 'warnings': actual_issues})
            progress(f'Sayfa {page_id}: {"mevcut çıktı" if reused else "kaydedildi"}; uyarı: {len(actual_issues)}')
        except (ExportError, OSError, ValueError, KeyError) as exc:
            summary['failed'] += 1
            log({'event': 'page_error', 'id': page_id, 'error': str(exc)})
            progress(f'Sayfa {page_id}: hata, rapora kaydedildi')

    try:
        if root_page_id:
            pending, traversed = deque([root_page_id]), set()
            while pending:
                page_id = pending.popleft()
                if page_id in traversed:
                    continue
                traversed.add(page_id)
                collect(page_id)
                try:
                    for child in client.items(f'rest/api/content/{page_id}/child/page?limit=50'):
                        pending.append(str(child['id']))
                except (ExportError, KeyError, ValueError) as exc:
                    failure(f'children:{page_id}', exc)
        else:
            spaces = []
            if space_key:
                spaces = [{'key': space_key}]
            else:
                statuses = ['current', 'archived'] if include_archived_spaces else ['current']
                for status in statuses:
                    try:
                        spaces.extend(client.items('rest/api/space?' + urlencode({'limit': 50, 'status': status})))
                    except (ExportError, ValueError) as exc:
                        failure(f'spaces:{status}', exc)
            visited_spaces = set()
            for space in spaces:
                key = space.get('key')
                if not key:
                    failure('space', 'Space key eksik')
                    continue
                if key in visited_spaces:
                    continue
                visited_spaces.add(key)
                summary['spaces'].append(space)
                # Content listing includes every hierarchy depth, not just home children.
                query = urlencode({'type': 'page', 'status': 'current', 'spaceKey': key, 'limit': 50})
                try:
                    for page in client.items('rest/api/content?' + query):
                        collect(page['id'])
                except (ExportError, KeyError, ValueError) as exc:
                    failure(f'space:{key}', exc)
        summary['status'] = 'partial' if summary['failed'] or summary['enumeration_errors'] else 'completed'
    except KeyboardInterrupt:
        summary['status'] = 'interrupted'
        raise
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        dump(output / f'run-{stamp}.summary.json', summary)
    return summary
