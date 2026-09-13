import re
from bs4 import BeautifulSoup
from markdownify import markdownify

def convert(storage, assets):
    soup = BeautifulSoup(storage, "html.parser")
    warnings, codes = [], {}
    macros = sorted({m.get("ac:name", "unknown") for m in soup.find_all("ac:structured-macro")})
    for macro in list(soup.find_all("ac:structured-macro")):
        if macro.parent is None:
            continue
        name = macro.get("ac:name", "unknown")
        if name in {"code", "plantuml", "plantumlrender", "mermaid"} and macro.find("ac:plain-text-body") is not None:
            body = macro.find("ac:plain-text-body")
            text = body.get_text() if body else ""
            parameter = macro.find("ac:parameter", attrs={"ac:name": "language"})
            language = parameter.get_text().strip() if parameter else (name if name != "code" else "")
            language = re.sub(r"[^a-zA-Z0-9_+.-]", "", language)
            fence = "`" * max(3, 1 + max([len(s) for s in re.findall(r"`+", text)] or [0]))
            key = f"CFEXPORTCODETOKEN{len(codes)}END"
            while key in storage:
                key += "X"
            if name != 'code':
                warnings.append(f'{name}: kaynak korundu; DSL akışı semantik olarak yorumlanmadı.')
            codes[key] = f"{fence}{language}\n{text}" + ("" if text.endswith("\n") else "\n") + fence
            replacement = soup.new_tag("p")
            replacement.string = key
            macro.replace_with(replacement)
        else:
            warnings.append(f"Makro tam dönüştürülmedi: {name}; kaynak raw.json içinde korundu.")
            note = soup.new_tag("p")
            note.string = f"[Dönüştürülmemiş Confluence makrosu: {name}]"
            macro.insert_before(note)
            rich = macro.find("ac:rich-text-body", recursive=False)
            if rich:
                macro.replace_with(rich)
            else:
                macro.decompose()
    for item in list(soup.find_all("ac:image")):
        attachment = item.find("ri:attachment")
        filename = attachment.get("ri:filename") if attachment else None
        foreign = attachment and (attachment.find("ri:page") or attachment.find("ri:space"))
        path = assets.get(filename) if not foreign else None
        if path:
            image = soup.new_tag("img", src=path, alt=filename)
            item.replace_with(image)
        else:
            warnings.append(f"Görsel çözülemedi: {filename or 'harici görsel'}")
            item.replace_with(f"[Çözülemeyen görsel: {filename or 'harici görsel'}]")
    for link in list(soup.find_all("ac:link")):
        warnings.append("Confluence iç bağlantısı henüz çözümlenmedi.")
        link.replace_with(f"[Confluence bağlantısı: {link.get_text() or str(link)}]")
    remaining = sorted({tag.name for tag in soup.find_all() if ':' in tag.name and tag.name != 'ac:rich-text-body'})
    if remaining:
        warnings.append("Özel öğeler için kaynak JSON'u inceleyin: " + ", ".join(remaining))
    result = markdownify(str(soup), heading_style="ATX")
    for key, code in codes.items():
        result = result.replace(key, code)
    return result.strip() + "\n", list(dict.fromkeys(warnings)), macros
