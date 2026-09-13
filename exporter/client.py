import os
from urllib.parse import urljoin, urlsplit
import requests
from atlassian import Confluence
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class ExportError(Exception):
    pass

class ConfluenceClient:
    def __init__(self):
        self.base = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")
        token = os.environ.get("CONFLUENCE_PAT", "").strip()
        parsed = urlsplit(self.base)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ExportError("CONFLUENCE_BASE_URL geçerli bir HTTPS ana adresi olmalı.")
        if not token:
            raise ExportError("CONFLUENCE_PAT .env içinde tanımlanmalı.")
        self.session = requests.Session()
        self.session.verify = os.environ.get("CONFLUENCE_CA_BUNDLE") or True
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504], allowed_methods=["GET"])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.api = Confluence(
            url=self.base,
            token=token,
            cloud=False,
            session=self.session,
            timeout=60,
            # Retry is owned by our bounded GET-only HTTPAdapter.
            retry_with_header=False,
            backoff_and_retry=False,
        )

    def resolve(self, link):
        # REST links may include the context path or start at /rest or /download.
        context = urlsplit(self.base).path.rstrip("/")
        if context and (link.startswith("/rest/") or link.startswith("/download/")):
            link = context + link
        url = urljoin(self.base + "/", link)
        origin, target = urlsplit(self.base), urlsplit(url)
        if (target.scheme, target.hostname, target.port) != (origin.scheme, origin.hostname, origin.port) or target.username:
            raise ExportError("Farklı sunucuya kimlik bilgisi gönderimi engellendi.")
        return url

    def get(self, link, **kwargs):
        try:
            url = self.resolve(link)
            if kwargs.pop("stream", False):
                # The SDK request method buffers responses. Reuse its authenticated
                # session for bounded-memory binary downloads.
                response = self.session.get(url, timeout=(10, 60), allow_redirects=False, stream=True, **kwargs)
            else:
                response = self.api.request(
                    method="GET", path=url, absolute=True,
                    advanced_mode=True, allow_redirects=False, **kwargs
                )
        except requests.RequestException:
            raise ExportError("Bağlantı kurulamadı. VPN, DNS, proxy ve CA sertifikasını kontrol edin.") from None
        if 300 <= response.status_code < 400:
            response.close()
            raise ExportError("Yönlendirme alındı. Ana adresi ve SSO/PAT API erişimini kontrol edin.")
        if not response.ok:
            status = response.status_code
            response.close()
            raise ExportError(f"Confluence HTTP {status}. 401: PAT; 403: izin; 404: adres/sayfa veya erişim.")
        return response

    def json(self, link, **kwargs):
        with self.get(link, **kwargs) as response:
            try:
                data = response.json()
            except ValueError:
                raise ExportError("JSON yerine farklı yanıt alındı; SSO ve ana adresi kontrol edin.") from None
            if not isinstance(data, dict):
                raise ExportError("Beklenmeyen API yanıt biçimi.")
            return data

    def items(self, link):
        seen = set()
        while link:
            absolute = self.resolve(link)
            if absolute in seen:
                raise ExportError("API sayfalama döngüsü algılandı.")
            seen.add(absolute)
            data = self.json(absolute)
            if not isinstance(data.get("results"), list):
                raise ExportError("API yanıtında results listesi eksik.")
            yield from data["results"]
            link = data.get("_links", {}).get("next")

    def download(self, link, target):
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            with self.get(link, stream=True, headers={"Accept": "*/*"}) as response:
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(65536):
                        output.write(chunk)
            temporary.replace(target)
        except requests.RequestException:
            raise ExportError("Ek dosya indirilirken bağlantı kesildi.") from None
        finally:
            temporary.unlink(missing_ok=True)
