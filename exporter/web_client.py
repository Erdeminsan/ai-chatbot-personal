"""Independent, bounded HTTP client for the public web (no Confluence PAT)."""
from urllib.parse import urldefrag, urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .client import ExportError


def web_url(value, base=None):
    url = urldefrag(urljoin(base or '', value))[0]
    parsed = urlsplit(url)
    try:
        parsed.port  # Validate malformed/non-numeric ports before making a request.
    except ValueError:
        raise ExportError('Geçersiz URL portu.') from None
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ExportError('Kullanıcı bilgisi içermeyen bir HTTP/HTTPS adresi girin.')
    return url


class WebClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'ContextMarkdownExporter/1.0', 'Accept': '*/*'})
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504],
                      allowed_methods=['GET'])
        for scheme in ('http://', 'https://'):
            self.session.mount(scheme, HTTPAdapter(max_retries=retry))

    def fetch(self, url, *, limit=10 * 1024 * 1024):
        """Return (bytes, final URL, content type); validate each redirect."""
        url = web_url(url)
        try:
            for _ in range(6):
                with self.session.get(url, timeout=(10, 60), stream=True, allow_redirects=False) as response:
                    if 300 <= response.status_code < 400:
                        location = response.headers.get('Location')
                        if not location:
                            raise ExportError('Yönlendirme adresi eksik.')
                        url = web_url(location, url)
                        continue
                    if not response.ok:
                        raise ExportError(f'Web HTTP {response.status_code}: {url}')
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > limit:
                            raise ExportError(f'İndirme boyut sınırını aşıyor: {limit} bayt.')
                        chunks.append(chunk)
                    return b''.join(chunks), url, response.headers.get('Content-Type', '')
            raise ExportError('Çok fazla web yönlendirmesi.')
        except requests.RequestException:
            raise ExportError(f'Web bağlantısı kurulamadı: {url}') from None

    def close(self):
        self.session.close()
