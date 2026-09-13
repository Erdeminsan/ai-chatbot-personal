import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from .client import ExportError
from .parser import convert
from .enrichment import EnrichmentOptions, enrich_attachment, enrichment_markdown

def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def export_page(client, page_id, output, *, options=None, resume=False):
    options = options or EnrichmentOptions()
    if not re.fullmatch(r"[0-9]+", page_id):
        raise ExportError("Sayfa ID yalnızca rakamlardan oluşmalı.")
    raw = client.json(f"rest/api/content/{page_id}", params={"expand": "body.storage,version,space,ancestors"})
    if raw.get("type") != "page" or "storage" not in raw.get("body", {}):
        raise ExportError("Yanıtta page türü veya body.storage eksik.")
    version = str(raw.get("version", {}).get("number", ""))
    if not version.isdigit():
        raise ExportError("Sayfa sürümü eksik.")
    destination = Path(output).resolve() / page_id / version
    if destination.exists() and resume:
        previous = json.loads((destination / 'normalized.json').read_text(encoding='utf-8'))
        if previous.get('source_base_url') != client.resolve('./'):
            raise ExportError('Mevcut çıktı başka bir Confluence adresine ait; farklı --output kullanın.')
        if previous.get('enrichment_options') != options.metadata():
            raise ExportError('Mevcut çıktı farklı işlem ayarlarıyla üretildi; farklı --output kullanın.')
        if previous.get('status') == 'needs_review':
            raise ExportError('Mevcut çıktı uyarılı; ekleri yeniden denemek için farklı --output kullanın.')
        return destination, ['existing_version_reused']
    if destination.exists():
        raise ExportError("Bu sürüm zaten dışa aktarılmış. Yeniden denemek için farklı --output kullanın.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".export-", dir=destination.parent))
    try:
        dump(stage / "raw.json", raw)
        attachments = list(client.items(f"rest/api/content/{page_id}/child/attachment?limit=50"))
        dump(stage / "attachments.raw.json", attachments)
        (stage / "assets").mkdir()
        assets, records, issues = {}, [], []
        for attachment in attachments:
            title = attachment.get("title", "attachment")
            ident = str(attachment.get("id", ""))
            if not ident.isdigit():
                issues.append(f"Geçersiz ek ID: {title}")
                continue
            safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", title)[:120] or "attachment"
            path = "assets/" + ident + "_" + safe_name
            record = {"id": ident, "title": title, "version": attachment.get("version"), "path": None}
            try:
                download = attachment.get("_links", {}).get("download")
                if not download:
                    raise ExportError("İndirme bağlantısı yok.")
                client.download(download, stage / path)
                record["path"] = path
                digest = hashlib.sha256()
                with (stage / path).open("rb") as stream:
                    for chunk in iter(lambda: stream.read(65536), b""):
                        digest.update(chunk)
                record["sha256"] = digest.hexdigest()
                assets[title] = path
            except ExportError as exc:
                record["error"] = str(exc)
                issues.append(f"Ek indirilemedi: {title}: {exc}")
            if record['path']:
                record['enrichment'], enrichment_issues = enrich_attachment(stage / record['path'], title, options)
                issues.extend(f"{title}: {message}" for message in enrichment_issues)
            records.append(record)
        storage = raw["body"]["storage"]["value"]
        markdown, warnings, macros = convert(storage, assets)
        issues.extend(warnings)
        markdown += enrichment_markdown(records)
        # Concurrent edits must not be silently paired with the earlier page body.
        latest = client.json(f"rest/api/content/{page_id}", params={"expand": "version"})
        if latest.get("version", {}).get("number") != raw["version"]["number"]:
            raise ExportError("Sayfa dışa aktarım sırasında değişti; tekrar deneyin.")
        source = client.resolve(raw.get("_links", {}).get("webui", f"pages/viewpage.action?pageId={page_id}"))
        normalized = {
            "schema_version": 2, "source_base_url": client.resolve("./"), "enrichment_options": options.metadata(), "page_id": page_id, "title": raw["title"],
            "space": raw.get("space", {}).get("key"), "version": int(version),
            "source_url": source, "ancestors": [{"id": x["id"], "title": x.get("title")} for x in raw.get("ancestors", [])],
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "storage": storage, "markdown": markdown, "attachments": records,
            "macro_names": macros, "generated_content_requires_review": any(r.get("enrichment", {}).get("vision") for r in records), "warnings": issues,
            "acl_status": "not_collected", "scope": "single_current_page_and_direct_attachments",
            "status": "needs_review" if issues else "converted",
        }
        dump(stage / "normalized.json", normalized)
        (stage / "page.md").write_text("# " + raw["title"] + "\n\nKaynak: " + source + "\n\n" + markdown, encoding="utf-8")
        stage.rename(destination)
        return destination, issues
    finally:
        if stage.exists():
            shutil.rmtree(stage)
