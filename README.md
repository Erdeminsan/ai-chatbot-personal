# Confluence Exporter — toplu tarama, OCR ve diyagram işleme

Confluence Data Center 8.5.3 hedefli Django komut projesi. atlassian-python-api 5.0.4 ile API istekleri, requests ortak oturumuyla ek indirme yapılır. Veri tabanı ve web arayüzü yoktur: `migrate` ve `runserver` gerekmez. Python 3.12/3.13 kullanın.

## Kurulum

 `confluence_exporter` klasörüne geçin. Mevcut `.env` dosyanızı koruyun.

```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Son satır yalnızca ilk kurulum içindir; mevcut .env dosyanızın üzerine yazmayın.
Windows PowerShell'de etkinleştirme: `venv\Scripts\Activate.ps1`; dosya kopyalama: `Copy-Item .env.example .env`.

.env içinde:

```dotenv
CONFLUENCE_BASE_URL=https://confluence.sirketiniz.com/confluence
CONFLUENCE_PAT=KENDI_PAT_DEGERINIZ
CONFLUENCE_CA_BUNDLE=
TESSERACT_CMD=
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=
```

Ana adreste kurumunuz /confluence kullanmıyorsa bu kısmı kaldırın. Sayfa URL'si veya /rest/api eklemeyin. Özel CA varsa CONFLUENCE_CA_BUNDLE değerine PEM dosyası yolunu yazın. TLS doğrulaması açık kalır. Confluence'a erişebilen şirket ağı/VPN gerekir. PAT çıktılara eklenmez.

```bash
python manage.py check_confluence
```

## Tek sayfa, space ve tüm sayfa ağacı

```bash
# Tek sayfa, doğrudan ekleri ve varsa draw.io kaynak analizi
python manage.py export_page --page-id 123456

# Bir space içindeki bütün güncel sayfalar; her derinlikteki alt sayfalar dahil
python manage.py export_confluence --space-key ENG --output exports_eng

# Seçili sayfa ve tüm alt sayfaları (torunlar dahil)
python manage.py export_confluence --root-page-id 123456 --output exports_tree

# Hesabın görebildiği bütün güncel space'ler ve içlerindeki güncel sayfalar
python manage.py export_confluence --all-spaces --output exports_all

# Arşivlenmiş space'leri de space keşfine dahil et
python manage.py export_confluence --all-spaces --include-archived-spaces --output exports_with_archived
```

`--all-spaces`, `--space-key`, `--root-page-id` seçeneklerinden yalnızca birini seçin. Space listelemesi ve içerik/ek/çocuk listelemelerinde `_links.next` takip edilir. Space içerik listesi yalnızca ana sayfaları değil bütün derinlikleri kapsar; ağaç seçeneği ise çocuk endpoint'ini kuyrukla dolaşır. Aynı kimlik tek koşuda yalnızca bir kez işlenir. Döngü, eksik izin ve listeleme hataları raporlanır. API hesabının göremediği içerikler keşfedilemez.

Toplu komutta --output verilmezse exports_batch altında zamana göre yeni bir klasör oluşturulur. Sayfalar sıralı işlenir; paralel istek yapılmaz. Bir sayfa başarısız olduğunda diğer sayfalara devam edilir. Ctrl+C durumunda biten sayfalar ve rapor saklanır.

## OCR: görsel içindeki Türkçe/İngilizce yazıyı çıkarma

Mac'te Homebrew ile:

```bash
brew install tesseract tesseract-lang
tesseract --list-langs
```

Linux/Debian:

```bash
sudo apt install tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng
```

Dil listesinde `tur` ve `eng` bulunmalı. Yalnızca İngilizce dil paketi varsa `--ocr-lang eng` kullanın. Motor PATH üzerinde değilse TESSERACT_CMD ortam değişkenine tam yolunu girin.

```bash
python manage.py export_page --page-id 123456 --ocr --output exports_ocr
python manage.py export_confluence --all-spaces --ocr --ocr-lang tur+eng --output exports_all_ocr
```

OCR yerelde Tesseract ile çalışır. PNG/JPEG/WebP/BMP/TIFF/GIF ekleri desteklenir. Çıktıda metin, kelime kutuları ve motorun güven puanları bulunur. Güven puanı doğruluk garantisi değildir. OCR metni kaynak sayfa metninden ayrı tutulur. Çok kareli görüntülerde yalnızca ilk kare işlenir ve uyarı yazılır. PDF/Office eklerinin içindeki görseller ve SVG rasterizasyonu bu sürümün kapsamı dışındadır. OCR resimdeki okları yorumlamaz.

## Diyagram işleme

**draw.io kaynakları otomatik işlenir.** `.drawio` uzantısı veya içeriğinde `<mxfile>` / `<mxGraphModel>` bulunan ekler tanınır. Sıkıştırılmış ve sıkıştırılmamış XML, birden fazla diyagram sayfası, normal hücreler ve object/UserObject düğümleri desteklenir. Düğüm kimlikleri/etiketleri, bağlantı uçları, bağlantı etiketleri ve belirtilmiş ok stilleri JSON'a yazılır. İnsan tarafından okunabilir yapı Markdown'a eklenir. Belirtilmemiş ok stili için akış yönü uydurulmaz.

PlantUML/Mermaid makrolarında plain-text-body bulunuyorsa kaynak DSL kod bloğu olarak korunur. Bu DSL'ler render edilmez veya tam semantik analize tabi tutulmaz. Diğer makrolar uyarı bırakır ve orijinal storage JSON içinde korunur. draw.io makrosu ile kaynak eki otomatik birebir eşlenmediği için başarılı kaynak analizi yanında makro uyarısı görülebilir.

**Sadece görsel olan diyagramların açıklaması için yerel Ollama görsel modeli:**

1. Ollama kurun ve çalıştırın.
2. Bilgisayarınızda çalışabilen, görsel girdisi destekleyen bir model indirin.
3. `ollama list` çıktısındaki model adını `.env` içindeki `OLLAMA_MODEL` alanına yazın.
4. `--vision` seçeneğiyle çalıştırın:

```bash
python manage.py export_page --page-id 123456 --ocr --vision --output exports_vision
python manage.py export_confluence --space-key ENG --ocr --vision --output exports_eng_vision
```

Vision yalnızca --vision verilirse çağrılır. Bu sürüm yalnızca localhost/127.0.0.1/::1 Ollama adreslerine bağlanır. Confluence PAT'ı Ollama'ya gönderilmez; ayrı oturum kullanılır. Model bilgisayarınızda kurulu ve çalışır olmalıdır; proje model indirmez. Görseller en fazla 2048 piksel boyutuna küçültülerek modele gönderilir. Bu nedenle küçük yazılar kaybolabilir.

Model bütün desteklenen raster ekleri inceler; yalnızca dosya adından diyagram tahmini yapılmaz. Diyagram değilse kısa görsel açıklaması üretmesi istenir. Üretilen metin `generated=true`, `requires_review=true` ile saklanır. Model açıklaması kaynak gerçek olarak kabul edilmez. Model hatasında sayfa korunur, eksik analiz uyarıya yazılır. Gliffy veya eklentiye özel depodaki diyagram için erişilebilir raster önizleme eki yoksa bu sürüm onu yorumlayamaz; eklentiye özel adaptör gerekir.

## Çıktılar ve hata takibi

Her sayfa `<output>/<page-id>/<version>/` altında:

| Dosya | İçerik |
| --- | --- |
| raw.json | Değiştirilmemiş sayfa API yanıtı |
| attachments.raw.json | Doğrudan eklerin metadata'sı |
| normalized.json | Şema v2: metadata, storage, Markdown, ekler, OCR, diyagram grafiği, model yorumu, uyarılar |
| page.md | Sayfa ve ayrı bölümde eklerden çıkarılan bilgiler |
| assets/ | Orijinal indirilen dosyalar |

Toplu taramada ayrıca `run-*.jsonl` olay raporu ve `run-*.summary.json` özet oluşur. Özet kaydedilen, tekrar kullanılan, uyarılı, başarısız sayfaları ve listeleme hatalarını ayrı sayar. `completed` listelemenin bitmesini ifade eder; uyarısız dönüşüm veya model doğruluğu garantisi değildir. Model yorumlarının inceleme gerekliliği normalized.json içindeki `generated_content_requires_review` alanında ayrıca belirtilir.

Başarısız sayfa/listeleme varsa komut sıfırdan farklı çıkış koduyla biter. İndirilemeyen ek veya OCR/model hatası sayfayı `needs_review` yapar; diğer içerik korunur.

```bash
python manage.py export_confluence --all-spaces --output exports_all --resume
```

Resume tekrar envanter çıkarır ve aynı kaynak/sayfa sürümü/analiz ayarlarıyla üretilmiş uyarısız çıktıları yeniden kullanır. Uyarılı çıktıları sessizce başarılı saymaz; yeni --output ile yeniden işleyin. Önceki v1 çıktıları veya farklı OCR/model ayarları için yeni klasör kullanın. Resume gerçek artımlı senkronizasyon değildir: bağımsız ek değişikliklerini, silinmeleri, yetki değişimlerini veya modelin aynı isim altındaki güncellemesini tespit etmez. Güncel tam çıktı gerektiğinde yeni --output kullanın.

## Sınırlar

- Güncel sayfalar ve doğrudan ekler kapsam dahilindedir. Bloglar, yorumlar, sürüm geçmişi, taslaklar, çöp kutusu dahil değildir. Arşiv space seçeneği sayfa status=current filtresini değiştirmez.
- ACL henüz çıkarılmaz (`acl_status=not_collected`); farklı izinli kullanıcılar için ortak arama indeksine erişim denetimi ayrıca eklenmelidir.
- Başka sayfaya referans veren görseller, sayfa içi Confluence bağlantıları ve include makroları henüz çözümlenmez.
- Karmaşık tablolar ve eklenti makrolarında tam görünüm sadakati garanti edilmez; orijinal JSON saklanır.
- Sayfa sürümü işlem sonunda kontrol edilir; ekler ve tüm site için transaction/snapshot garantisi yoktur.
- Henüz LLM eğitimi veya RAG indeksi yoktur.

## Doğrulama

```bash
python manage.py check
python -m unittest exporter.tests exporter.test_bulk -v
```

19 test: SDK/PAT yapılandırması ve HTTP yanıtları (taklit yanıtlarla), sayfalama, tüm space/ağaç dolaşımı, hata sonrası devam, resume, draw.io sıkıştırma/çoklu sayfa/XML güvenliği, gerçek Tesseract İngilizce OCR, taklit Ollama yanıtı ve dosyaya uçtan uca diyagram dışa aktarımı. OCR testi için Tesseract ve eng paketi gerekir.

Şirket Confluence 8.5.3 bağlantısı ve gerçek Ollama modeli burada test edilmedi. Türkçe OCR dili kullanıcı ortamında kurulum sonrası doğrulanmalıdır.

## Belgeler

- https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/
- https://atlassian-python-api.readthedocs.io/
- https://tesseract-ocr.github.io/tessdoc/Installation.html
- https://docs.ollama.com/api/chat
- https://www.drawio.com/docs/manual/advanced/diagram-source-edit/
