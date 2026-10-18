# Web ve Confluence Exporter

Web sayfalarındaki veya Confluence Data Center içindeki bilgileri; metin, görsel, kod ve diyagram kaynaklarını koruyarak **Markdown ve JSON dosyalarına** aktaran Python/Django komut satırı projesi.

**Kullanım sırası:** Önce Confluence erişimi olmadan web scraping ile sistemi çalıştırın. Çıktıları ve isteğe bağlı görsel analizini inceleyin. Confluence erişiminiz açıldığında aynı proje içinde bağlantı ayarlarını ekleyip Confluence komutlarına geçin.

## İçindekiler

1. [Web scraping ile ilk çalıştırma](#1-web-scraping-ile-ilk-çalıştırma)
2. [Web içeriğinin dönüştürülmesi](#2-web-içeriğinin-dönüştürülmesi)
3. [Web için OCR ve görsel model kurulumu](#3-web-için-ocr-ve-görsel-model-kurulumu)
4. [Web çıktıları ve sorun giderme](#4-web-çıktıları-ve-sorun-giderme)
5. [İki veri kaynağı ve ortak proje yapısı](#5-iki-veri-kaynağı-ve-ortak-proje-yapısı)
6. [Web denemesinden Confluence kullanımına geçiş](#6-web-denemesinden-confluence-kullanımına-geçiş)
7. [Confluence çıktıları ve çalışma sınırları](#7-confluence-çıktıları-ve-çalışma-sınırları)
8. [Dosyaların görevleri](#8-dosyaların-görevleri)
9. [Testler ve sonraki RAG aşaması](#9-testler-ve-sonraki-rag-aşaması)
10. [Komut başvurusu: bütün komutlar ve seçenekler](#10-komut-başvurusu-bütün-komutlar-ve-seçenekler)

## 1. Web scraping ile ilk çalıştırma

### 1.1. Şu anda neyi çalıştırıyoruz?

Komut satırına bir URL veriyoruz. Proje bu URL'nin döndürdüğü HTML'i indiriyor, ana içeriği seçiyor, metinleri ve görselleri işliyor; sonucu bilgisayarımızda dosyalara kaydediyor.

Bu adımda Confluence'a bağlanılmaz. **Confluence hesabı, PAT veya şirket VPN'i gerekmez.** Hedef sayfaya bilgisayarınızdan erişebilmeniz yeterlidir; sitenin kendi erişim kısıtlamaları ayrıca geçerlidir.

Varsayılan kapsam **tek URL'deki tek sayfadır**. Ana sayfayı vermek sitenin bütün bağlantılarının ve alt sayfalarının taranacağı anlamına gelmez.

Proje Django'nun komut altyapısını kullanır. Şu an veritabanı, web ekranı veya sohbet arayüzü yoktur. Çalıştırmak için `migrate` veya `runserver` gerekmez.

### 1.2. Kurulum

Python 3.12 veya 3.13 kullanın. Projeyi ilk kez indiriyorsanız:

```bash
git clone https://github.com/Erdeminsan/ai-chatbot-personal.git
cd ai-chatbot-personal
```

Proje zaten bilgisayarınızdaysa yeniden klonlamayın. Güncel kodu aldıktan sonra `manage.py` dosyasının bulunduğu klasöre geçin. Aşağıdaki bütün proje komutları bu klasörde çalıştırılır.

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python manage.py check
```

Windows PowerShell:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py check
```

Sonraki terminal oturumlarında sanal ortamı yeniden etkinleştirin; her seferinde oluşturmayın. `requirements.txt`, iki kaynağın Python bağımlılıklarını da kurar. Confluence paketinin kurulu olması Confluence'a bağlantı yapıldığı anlamına gelmez.

### 1.3. İlk web komutu

```bash
python manage.py export_web --url "https://ornek.com/dokuman" --output exports_web
```

Örnek URL yerine okumak istediğiniz gerçek HTML sayfasının adresini yazın. Özellikle `?` ve `&` içeren adreslerde URL'yi tırnak içinde tutun.

Bu komut için `.env` oluşturmak gerekmez. **OCR ve vision varsayılan olarak kapalıdır.** Metinler, tablolar, kodlar ve görsel dosyaları yine aktarılır; görselin içindeki yazılar okunmaz veya anlamına dair model yorumu üretilmez.

Terminalde oluşturulan `page.md` dosyasının tam yolu yazdırılır. Bu dosyayı bir editörde açın. Görsellerin görünmesi için Markdown dosyasıyla aynı çıktı klasöründeki `assets/` dizinini birlikte tutun.

### 1.4. Dış site gerektirmeyen hazır örnek

`examples/web_demo.html`; metin, açıklamalı SVG flow diyagramı, Mermaid sequence diagram, JSON kod bloğu ve tablo içerir.

Birinci terminalde proje klasöründen örnek sayfayı yayınlayın:

```bash
python -m http.server 8000 --bind 127.0.0.1 --directory examples
```

Bu terminal açık kalsın. İkinci terminalde aynı proje klasörüne geçip sanal ortamı etkinleştirin ve:

```bash
python manage.py export_web --url "http://127.0.0.1:8000/web_demo.html" --output exports_demo
```

Örnek sunucuyu birinci terminalde `Ctrl+C` ile durdurabilirsiniz. Bu sunucu yalnızca HTML örneğini sunar; Django `runserver` değildir. Örnekteki görsel SVG olduğu için SVG aktarımı ve kaynak kod korunması denenir. Raster görsel OCR/vision denemesi için PNG/JPEG içeren bir sayfa kullanın.

### 1.5. Web komutunun seçenekleri

| Seçenek | Varsayılan | Görevi |
| --- | --- | --- |
| `--url` | Zorunlu | Okunacak HTTP/HTTPS HTML sayfası |
| `--output` | `exports_web` | Çıktı klasörlerinin oluşturulacağı ana dizin |
| `--selector` | Otomatik | Ana içerik için CSS ifadesi; örneğin `#content` |
| `--ocr` | Kapalı | Raster görsellerdeki yazıları Tesseract ile çıkarır |
| `--ocr-lang` | `tur+eng` | `--ocr` için dil seçimi |
| `--vision` | Kapalı | Raster görselleri yerel Ollama modeliyle yorumlar |

Yardım: `python manage.py export_web --help`.

## 2. Web içeriğinin dönüştürülmesi

### 2.1. Ana içeriği seçme

`--selector` yoksa HTML'de önce `main`, yoksa `article`, sonra `body` seçilir; bunlar da yoksa tüm belge kullanılır. Navigasyon, footer, aside, form, script/style, template, noscript ve açıkça gizlenmiş öğeler çıkarılır. Her sitenin HTML yapısı farklı olduğundan otomatik seçim fazla veya eksik içerik alabilir.

Hedef alanı kendiniz belirlemek için:

```bash
python manage.py export_web --url "https://ornek.com/dokuman" --selector "#content"
python manage.py export_web --url "https://ornek.com/dokuman" --selector "article"
```

CSS seçicisi hangi HTML alanının okunacağını belirtir: `<div id="content">` için `#content`, `<div class="article-body">` için `.article-body` kullanılır. Geçersiz seçici veya eşleşmeyen alan komutu hatayla sonlandırır.

### 2.2. İçerik türleri

| Sayfadaki içerik | Çıktıda ne olur? |
| --- | --- |
| Başlık, paragraf, liste | Sayfa sırası korunarak Markdown'a çevrilir |
| Tablo | Markdown tabloya çevrilir; karmaşık yerleşimin birebir korunması garanti edilmez |
| Kod bloğu | Dil bilgisi varsa korunarak Markdown kod bloğu oluşturulur |
| Bağlantı | Göreli web adresleri sayfanın/base etiketinin adresine göre çözülür |
| PNG/JPEG/WebP/BMP/TIFF/GIF | İndirilip yerel `assets/` bağlantısıyla Markdown'a eklenir |
| Inline SVG veya SVG görsel | Kaynağı saklanır; başlık, açıklama ve metin etiketleri çıkarılır |
| Yaygın lazy-load, srcset, gömülü data URL | Desteklenen HTML biçimlerinde görsel kaynağı çözülür |

Sayfanın ekran görüntüsü alınmaz. HTML'deki bilgi ve desteklenen görsel kaynakları okunur; CSS arka plan görselleri bu kapsamda değildir.

### 2.3. Görsel ve açıklaması nasıl birlikte tutulur?

Teknik bir görsel açıklamasından koparıldığında anlamı kaybolabilir. Web aktarımı bu nedenle **görsel grupları** oluşturur. İlişki şu sırayla aranır:

1. Bir `figure` içindeki görseller ve `figcaption` aynı gruba alınır. Bir açıklama birden fazla görseli anlatıyorsa görseller birlikte tutulur.
2. Görseldeki `aria-describedby` açıklama öğesini işaret ediyorsa bu metin gruba eklenir.
3. Açık ilişki yoksa doğrudan komşu kısa açıklama/paragraf aranır. Paragraf eşleşmesi tahminidir: `adjacent_text_heuristic` ve **Yakın bağlam (otomatik eşleştirme)** etiketiyle saklanır. Açıklama sınıfı gibi açık bir komşu öğe `adjacent_caption` olarak kaydedilebilir.

Komşu metnin asıl sayfa konumu korunur; grupta bağlam için bir kopyası bulunabilir. Bu nedenle aynı paragrafın iki yerde görünmesi bazen beklenen davranıştır. Uzak metinler ve sitenin özel yerleşimleri her zaman doğru eşleştirilemez.

Bir grubun basitleştirilmiş görünümü:

```markdown
<!-- media-group:1 -->
![Sipariş akışı](assets/ornek.png)

Şekil 1: Ödeme başarılıysa hazırlama aşamasına geçilir.

**media-1-1 — OCR metni:**
> Görseldeki yazılar

**media-1-1 — Model yorumu — doğrulama gerekli:**
> Modelin ürettiği açıklama
<!-- /media-group:1 -->
```

OCR/model bölümleri yalnızca ilgili seçenek kullanılıp sonuç üretildiğinde bulunur. Aynı grup JSON'daki `media_groups` içinde de saklanır: açıklama ilişkisinin yöntemi, görsel dosyaları ve analizler bir aradadır.

`--vision` açıkken alt metin, ilişkili açıklama ve grup metni de görselle birlikte modele gönderilir; metin bağlamı en fazla 6000 karakterdir. Modelden bağlamın iddiasıyla görselde doğrudan gördüklerini ayırması istenir. Aynı görsel farklı açıklamalarla tekrar kullanılırsa dosya bir kez indirilir, her kullanım kendi bağlamıyla analiz edilir.

### 2.4. Sequence diagram ve flow diyagramları

İşleme biçimini diyagramın sayfada nasıl sunulduğu belirler:

| Biçim | Yapılan işlem | Akış yorumlanıyor mu? |
| --- | --- | --- |
| Tanınan Mermaid/PlantUML/sequence/Graphviz/DOT kaynak bloğu | Dil etiketli Markdown kod bloğunda ve JSON `diagrams` alanında korunur | Kaynak korunur; tam semantik çözümleme veya render yapılmaz |
| PNG/JPEG gibi raster diyagram | İndirilip varsa açıklamasıyla gruplanır | `--vision` ile model yorumu üretilebilir |
| Raster görsel içindeki yazılar | `--ocr` ile metin, kelime kutuları ve güven puanları çıkarılır | OCR tek başına okları veya mesaj sırasını yorumlamaz |
| SVG diyagram | SVG kaynağı ve metin etiketleri korunur | Geometriden ok yönü çıkarılmaz; SVG için rasterizasyon/vision yoktur |
| Canvas, iframe veya yalnızca JavaScript ile oluşan diyagram | Tam içeriği işlenmez; gömülü öğeler uyarı bırakabilir | Hayır |

Markdown'da görsel bağlantısının bulunması diyagramın anlamının çözüldüğü anlamına gelmez. Kaynak metin, OCR çıktısı ve model yorumu farklı bilgi türleridir.

## 3. Web için OCR ve görsel model kurulumu

### 3.1. Hangi araca ne zaman ihtiyacım var?

| İhtiyaç | Gereken | Seçenek |
| --- | --- | --- |
| HTML metni ve görsel dosyaları | Python bağımlılıkları | Ek seçenek yok |
| Görsel içindeki yazılar | Tesseract motoru ve dil paketleri | `--ocr` |
| Raster görsel/sequence/flow açıklaması | Çalışan yerel Ollama ve görsel girdisi destekleyen model | `--vision` |
| İki analiz birlikte | Tesseract ve Ollama | `--ocr --vision` |

`pip install -r requirements.txt`, Tesseract motorunu, Ollama sunucusunu veya model dosyalarını kurmaz. Bunlar ayrı kurulur. OCR ve vision bağımsızdır; biri diğerini zorunlu kılmaz.

### 3.2. Tesseract OCR

macOS/Homebrew:

```bash
brew install tesseract tesseract-lang
tesseract --list-langs
```

Debian/Ubuntu:

```bash
sudo apt install tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng
tesseract --list-langs
```

Diğer Linux dağıtımlarında uygun motor/dil paketlerini kendi paket yöneticinizle kurun; `apt` komutu Red Hat için kullanılmaz. Windows'ta Tesseract ve gerekli dil dosyalarını ayrıca kurun.

`tur+eng` için dil listesinde ikisi de bulunmalıdır. Yalnızca İngilizce kuruluysa `--ocr-lang eng` kullanın:

```bash
python manage.py export_web --url "https://ornek.com/dokuman" --ocr --ocr-lang eng
python manage.py export_web --url "https://ornek.com/dokuman" --ocr --ocr-lang tur+eng
```

Motor PATH üzerinde değilse proje kökünde `.env` oluşturup tam yolunu yazın:

```dotenv
TESSERACT_CMD=/tam/yol/tesseract
```

OCR yerelde çalışır. Desteklenen görsellerde 25 megapiksel sınırı uygulanır. Çok kareli görsellerin yalnızca ilk karesi işlenir ve uyarı yazılır. PDF/Office içindeki görseller ve SVG rasterizasyonu desteklenmez. Güven puanı, metnin doğru okunduğunun garantisi değildir.

### 3.3. Yerel Ollama vision

1. Ollama'yı kurup yerel sunucuyu çalıştırın.
2. Bilgisayarınızın kaynaklarına uygun, **görsel girdisi destekleyen** bir model indirin.
3. `ollama list` ile kurulu modelin tam adını kontrol edin.
4. Bu adı proje kökündeki `.env` dosyasına yazın.

Komutların biçimi:

```bash
ollama pull MODEL_ADI
ollama list
```

`MODEL_ADI` bir yer tutucudur; gerçek bir görsel model adıyla değiştirin. Proje sizin yerinize model seçmez/indirmez. Yalnızca metin kabul eden model vision için yeterli değildir.

`.env`:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=KURULU_GORSEL_MODELIN_TAM_ADI
```

Model alanını gerçek kurulu model adıyla değiştirin. Kök adrese `/api/chat` eklemeyin; kod ekler. Sunucu zaten çalışıyorsa tekrar başlatmayın; gerektiğinde ayrı terminalde `ollama serve` kullanılır.

```bash
python manage.py export_web --url "https://ornek.com/dokuman" --vision
python manage.py export_web --url "https://ornek.com/dokuman" --ocr --ocr-lang tur+eng --vision
```

Yalnızca `localhost`, `127.0.0.1` ve `::1` üzerindeki Ollama adresleri kabul edilir. İstek ayrı HTTP oturumuyla gider; Confluence PAT'ı taşınmaz. Görseller 2048 × 2048 sınırına sığacak şekilde küçültülür; küçük yazılar kaybolabilir. Desteklenen raster görseller dosya adından diyagram tahmini yapılmadan incelenir.

Üretilen açıklama `generated=true`, `requires_review=true` ile işaretlenir. Model çıktısı kaynak sayfanın kesin bilgisi kabul edilmez. Çağrı başarısız olursa içerik korunur ve uyarı bırakılır.

### 3.4. `.env` dosyasını koruma

Örnek ayarları almak için **yalnızca `.env` henüz yoksa**:

```bash
cp .env.example .env
```

PowerShell: `Copy-Item .env.example .env`. Mevcut dosyanın üzerine kopyalamayın; gereken alanları düzenleyin. Web/OCR/vision için `CONFLUENCE_PAT` boş kalabilir. `.env`, sanal ortam ve `exports*` dizinleri `.gitignore` kapsamındadır.

## 4. Web çıktıları ve sorun giderme

### 4.1. Çıktı dosyaları

Her koşu `--output` dizininde yeni bir `<sunucu>_<zaman>_<benzersiz-ek>/` klasörü oluşturur. Örneğin: `exports_web/ornek_com_20261018T200000000000Z_a1b2c3/page.md`. Önceki koşunun üzerine yazılmaz.

| Dosya/JSON alanı | İçerik |
| --- | --- |
| `page.md` | Başlık, kaynak satırı ve dönüştürülen içerik |
| `raw.html` | Sunucunun döndürdüğü orijinal HTML |
| `normalized.json` | Kaynak metadata'sı, Markdown, görsel grupları ve analizler |
| `assets/` | İndirilen görseller ve SVG kaynakları |
| `requested_url` / `source_url` | Girilen adres / yönlendirme sonrası sayfa adresi |
| `markdown` | Dönüştürülen gövde; `page.md` ayrıca başlık ve kaynak ekler |
| `media_groups` | Görseller, açıklama ilişkileri, OCR ve vision sonuçları |
| `diagrams` | Tanınan diyagram kaynak blokları |
| `warnings` / `status` | Uyarılar ve `converted` / `needs_review` durumu |
| `generated_content_requires_review` | Başarılı bir vision yorumu bulunup bulunmadığı |

`converted`, model doğruluğunu onaylayan kalite damgası değildir. Başarılı model yorumu inceleme gerektirdiği halde işlem uyarısı oluşmamış olabilir; model inceleme alanını ayrıca kontrol edin.

### 4.2. Hata ile uyarı farkı

HTML indirilemiyorsa, URL HTML yerine PDF gibi başka içerik döndürüyorsa veya seçici geçersizse komut hatayla biter. Görsel indirilememesi/analiz hatası durumunda kalan içerik korunur; uyarılar JSON'a yazılır. Bu uyarılar komutu mutlaka sıfırdan farklı çıkış koduyla sonlandırmaz.

SVG akışının yorumlanmaması veya vision kapalıyken raster görselin yalnızca korunması gibi kapsam bilgileri de uyarı oluşturabilir. Uyarı görmek bütün aktarımın bozuk olduğunu göstermez.

| Durum | Kontrol |
| --- | --- |
| `manage.py` bulunamıyor | Proje kökünde olun |
| Python paketi bulunamıyor | Sanal ortamı etkinleştirip aynı Python ile bağımlılıkları kurun |
| Menü geldi/makale eksik | `--selector` ile doğru alanı seçin |
| Tarayıcıdaki içerik yok | JavaScript, iframe/canvas veya oturum gerekebilir; tarayıcı çalıştırılmaz |
| Giriş ekranı dışa aktarıldı | Web oturumu desteği yok; HTTP 200 gerçek makale alındığını garanti etmez |
| Görsel yazısı çıkmadı | `--ocr`, motor ve dil paketlerini kontrol edin |
| Diyagram açıklanmadı | `--vision`, Ollama ve görsel model gerekir; SVG için vision yok |
| Yanlış açıklama eşleşti | JSON'daki yöntem alanını inceleyin; komşu paragraf ilişkisi tahminidir |
| Model hatası | Ollama sunucusu, model adı ve görsel girdi desteği |
| Büyük dosyada aktarım durdu | Web HTML indirmesi 10 MiB, görsel indirmesi 20 MiB ile sınırlı |

Web komutunda `--resume` yoktur; tekrar çalıştırmak yeni çıktı üretir. Site genelini tarama, giriş yapma, PDF/Office işleme ve CSS arka plan görsellerini toplama henüz yoktur.

## 5. İki veri kaynağı ve ortak proje yapısı

**Web scraping ve Confluence aynı Python projesindedir.** İki ayrı veri toplama yolu bulunur. İkisini aynı anda çalıştırmak zorunda değilsiniz. Hangi komutu çalıştırırsanız o kaynağa bağlanılır; genel bir “mod değiştir” ayarı yoktur.

| Konu | Web scraping | Confluence |
| --- | --- | --- |
| Komut | `export_web --url ...` | `export_page --page-id ...` veya `export_confluence ...` |
| Kaynak | URL'nin döndürdüğü HTML | Confluence REST API |
| Kimlik doğrulama | Yerleşik giriş/oturum yok | PAT |
| Kullanıcı girdisi | URL, isteğe bağlı CSS seçicisi | Sayfa ID'si, space key veya tüm space seçimi |
| Kapsam | Tek sayfa | Tek sayfa, ağaç, bir space veya görünür tüm space'ler |
| Dönüştürücü | `web.py` | `parser.py` ve `service.py` |
| Analiz motoru | Ortak `enrichment.py` | Ortak `enrichment.py` |
| Ham kaynak | `raw.html` | `raw.json`, `attachments.raw.json` |
| JSON | Web şeması v1: `media_groups`, `diagrams` | Confluence şeması v3: `media_groups`, `attachments`, `storage` |

Confluence'a geçmek, web çıktısını Confluence'a yüklemek veya web sayfasını Confluence sayfasına çevirmek değildir. **Değişen şey veri kaynağını okuyan komut ve bağlantı ayarlarıdır.** Aynı sanal ortamı, Python bağımlılıklarını, Tesseract ve Ollama kurulumunu kullanırsınız.

### Her iki kaynakta görsel-açıklama gruplaması

Web tarafındaki `media_groups`, görseli açıklaması ve analizleriyle aynı grupta tutar; vision çağrısına grup metnini de gönderir.

**Confluence tarafında da görsel, ilişkili açıklama ve OCR/draw.io/vision sonuçları aynı `media_groups` grubunda tutulur.** Markdown'da grup, görselin sayfadaki yerinde `<!-- media-group:1 -->` sınırlarıyla yazılır. Vision çağrısına sayfa başlığı, görselin alt metni ve açıklama bağlamı da gönderilir. Aynı ek farklı yerlerde kullanılırsa dosya bir kez indirilir; her kullanım kendi bağlamıyla analiz edilir.

Confluence storage içindeki ilişkiler şu şekilde ele alınır:

| Kaynak alan/yapı | Davranış |
| --- | --- |
| `ac:image` içindeki `ac:caption` | Açıklama biçimlendirmesiyle korunur ve görselle gruplanır |
| `figure` / `figcaption` | Aynı şeklin görselleri ve ortak açıklaması birlikte tutulur |
| `aria-describedby` | İşaret edilen açıklama gruba eklenir |
| `ac:title` | Görsel başlık/ipuç metni olarak ayrıca saklanır; görünür caption olduğu varsayılmaz |
| `ac:alt` | Alt metin korunur ve modele bağlam sağlar |
| Görselle aynı paragraftaki metin | `inline_text` ilişkisiyle birlikte tutulur |
| Doğrudan komşu kısa paragraf | `adjacent_text_heuristic` olarak işaretlenir; kesin açıklama kabul edilmez |

Başka başlık veya tablo hücresinin ötesindeki metin bağlam diye alınmaz. Komşu açıklamalar asıl konumlarında da korunabilir. Başka sayfaya ait görsel referansı, aynı dosya adındaki yerel ekle eşleştirilmez; çözülemeyen görselin açıklaması kaybolmaz ve uyarı yazılır.

Sayfa içinde görsel olarak referans verilmeyen eklerin analizleri **Eklerden çıkarılan bilgiler** bölümünde kalır. Eklenti makrosunu bir draw.io ekiyle otomatik birebir eşleme henüz yapılmaz. Her iki kaynak ortak grup alanları sunar; kaynak metadata'sı ve JSON şemalarının tamamı hâlâ farklıdır.

## 6. Web denemesinden Confluence kullanımına geçiş

### 6.1. Geçiş sırası

Web üzerinde kullandığınız komut:

```bash
python manage.py export_web --url "https://ornek.com/dokuman" --ocr --vision
```

Confluence erişiminiz açıldığında aynı projede:

1. Şirket Confluence adresine erişebilen ağ/VPN bağlantısını açın.
2. PAT oluşturup `.env` içine ekleyin.
3. `check_confluence` ile bağlantıyı doğrulayın.
4. Önce tek sayfayı `export_page` ile alın.
5. Çıktıyı inceledikten sonra space/ağaç veya tüm space taramasına geçin.

Web çıktısını silmek, yeni Django projesi açmak veya Tesseract/Ollama'yı yeniden kurmak gerekmez. Kaynakları ayırmak için farklı `--output` dizinleri kullanın.

### 6.2. Bağlantı ayarları

Hedef **Confluence Data Center 8.5.3**; istemci `cloud=False` ve `atlassian-python-api==5.0.4` kullanır. Bu yapı Cloud e-posta/API token akışına göre hazırlanmamıştır.

Mevcut `.env` dosyanıza Confluence alanlarını ekleyin:

```dotenv
CONFLUENCE_BASE_URL=https://confluence.sirketiniz.com/confluence
CONFLUENCE_PAT=KENDI_PAT_DEGERINIZ
CONFLUENCE_CA_BUNDLE=
```

| Alan | Anlamı |
| --- | --- |
| `CONFLUENCE_BASE_URL` | HTTPS kök adresi; kurumunuz kullanıyorsa `/confluence` context path dahil |
| `CONFLUENCE_PAT` | Personal Access Token; API oturumunda Bearer kimliği olarak kullanılır |
| `CONFLUENCE_CA_BUNDLE` | Gerekirse kurumsal CA PEM dosyası yolu; boşsa sistem sertifikaları |
| `TESSERACT_CMD` | Varsa önceki OCR ayarı korunur; iki kaynakta ortak |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Önceki yerel görsel model ayarları korunur; iki kaynakta ortak |

Kök adrese sayfa yolu veya `/rest/api` eklemeyin. Kurumunuz context path kullanmıyorsa `/confluence` kısmını kaldırın. TLS doğrulaması açıktır. PAT normalleştirilmiş çıktılara bilerek eklenmez; ham dosyalar ise kaynağın sayfa/ek içeriğini taşır.

### 6.3. Bağlantıyı doğrulama

```bash
python manage.py check_confluence
```

Komut mevcut kullanıcı ve space API'sini kontrol eder. Başarı bütün sayfalara erişim olduğu anlamına gelmez; yalnızca hesabın izin verdiği içerikler keşfedilebilir.

| Hata/durum | Kontrol |
| --- | --- |
| HTTP 401 | PAT geçerliliği ve API erişimi |
| HTTP 403 | Sayfa/space yetkisi |
| HTTP 404 | Kök adres, context path, sayfa ID'si veya görünürlük |
| SSO yönlendirmesi / HTML yanıt | Doğru kök adres ve PAT ile REST API erişimi |
| Bağlantı/sertifika hatası | VPN, DNS, proxy ve kurumsal CA dosyası |
| Görünür space yok | Hesap izinleri |

### 6.4. İlk Confluence sayfası

Sayfa ID'si sayısal kimliktir; örneğin URL'de `pageId=123456` olarak görülebilir. Tam web URL'si yerine bu ID verilir:

```bash
python manage.py export_page --page-id 123456 --output exports_confluence_test
```

OCR ve vision ile:

```bash
python manage.py export_page --page-id 123456 --ocr --ocr-lang tur+eng --vision --output exports_confluence_test_vision
```

Bu komut yalnızca seçili güncel sayfayı ve doğrudan eklerini alır; **alt sayfaları almaz**. Storage gövdesi API'den çekilir, ekler indirilir ve analizler kaydedilir. İşlem sonunda sayfa sürümü yeniden kontrol edilir; değişmişse çıktı tamamlanmış gibi kaydedilmez.

### 6.5. Alt sayfalar ve toplu tarama

Sayfa ve bütün alt sayfaları, torunlar dahil:

```bash
python manage.py export_confluence --root-page-id 123456 --output exports_confluence_tree
```

Bir space'in bütün güncel sayfaları:

```bash
python manage.py export_confluence --space-key ENG --output exports_confluence_eng
```

`ENG` yerine gerçek space anahtarını kullanın. Space içerik listesi her derinlikteki sayfaları kapsar.

Hesabın görebildiği bütün güncel space'ler:

```bash
python manage.py export_confluence --all-spaces --output exports_confluence_all
```

Arşiv space'leri keşfe dahil etme:

```bash
python manage.py export_confluence --all-spaces --include-archived-spaces --output exports_confluence_with_archived
```

`--all-spaces`, `--space-key`, `--root-page-id` seçeneklerinden tam birini seçin. Arşiv seçeneği space keşfini genişletir; sayfalardaki `status=current` filtresini değiştirmez. OCR/vision toplu komutlarda da kullanılabilir:

```bash
python manage.py export_confluence --space-key ENG --ocr --ocr-lang tur+eng --vision --output exports_confluence_eng_vision
```

API listelerinde `_links.next` takip edilir; ağaç kuyrukla dolaşılır. Aynı sayfa bir koşuda bir kez işlenir. Sayfalar sıralı işlenir, paralel istek yapılmaz. Bir sayfa başarısız olursa diğerlerine devam edilir; listeleme hataları ayrıca raporlanır.

## 7. Confluence çıktıları ve çalışma sınırları

### 7.1. Çıktı dosyaları

Her sayfa `<output>/<page-id>/<version>/` altında tutulur. Örneğin `exports_confluence_test/123456/7/page.md`, 123456 numaralı sayfanın 7. sürümüdür. Tek sayfada varsayılan ana dizin `exports`; toplu komutta `--output` verilmezse `exports_batch/<zaman>/` kullanılır.

| Dosya | İçerik |
| --- | --- |
| `raw.json` | API'den alınan ham sayfa yanıtı |
| `attachments.raw.json` | Doğrudan eklerin metadata listesi |
| `normalized.json` | Şema v3: kaynak, ID, space, sürüm, storage, Markdown, ekler, görsel grupları ve analizler |
| `page.md` | Görsel grupları sayfadaki yerinde; kullanılmayan eklerin analizleri sonda |
| `assets/` | İndirilen orijinal ekler |

JSON'da `media_groups[].assets[].enrichment` alanı, o görsel kullanımına ait analizleri taşır. Grup varlıklarında `id` kullanım kimliği, `attachment_id` ise kaynak ekin kimliğidir. Kaynak `attachments` kayıtlarının `media_group_ids` listesi hangi gruplarda kullanıldıklarını gösterir. Görsel olarak referans verilmeyen ekler analizlerini kendi `attachments[].enrichment` alanlarında taşır. `warnings`, `status`, `generated_content_requires_review` ve `acl_status` alanlarını da kontrol edin.

Toplu tarama ayrıca `run-*.jsonl` olay raporu ve `run-*.summary.json` özeti üretir. Kaydedilen, tekrar kullanılan, uyarılı, başarısız sayfalar ve listeleme hataları ayrı sayılır. Ctrl+C ile kesilirse biten sayfalar ve özet korunur.

`completed`, listelemenin bitmesini ifade eder; bütün dönüşümlerin uyarısız veya modelin doğru olduğunu garanti etmez. Başarısız sayfa/listeleme varsa toplu komut sıfırdan farklı kodla biter. Ek indirme/OCR/model uyarıları sayfayı `needs_review` yapabilir; kalan içerik korunur.

### 7.2. Devam etme: `--resume`

```bash
python manage.py export_confluence --all-spaces --output exports_confluence_all --resume
```

Toplu resume için önceki `--output` açıkça verilmelidir. Envanter tekrar çıkarılır; aynı kaynak, sayfa sürümü ve analiz ayarlarıyla üretilmiş uyarısız çıktılar yeniden kullanılır. Tek sayfa komutunda da `--resume` vardır.

| Durum | Davranış |
| --- | --- |
| Aynı sürüm mevcut, resume yok | Üzerine yazmak yerine hata verir |
| Kaynak/sürüm/ayarlar aynı, çıktı uyarısız | Çıktıyı yeniden kullanır |
| Mevcut çıktı uyarılı | Sessizce başarılı saymaz; yeniden denemek için yeni çıktı dizini kullanın |
| Kaynak veya analiz ayarları farklı | Yeni çıktı dizini kullanın |
| Güncel tam dışa aktarım isteniyor | Yeni `--output` ile çalıştırın |

Resume gerçek artımlı senkronizasyon değildir. Bağımsız ek değişikliklerini, silinmeleri, yetki değişikliklerini veya aynı isim altındaki model güncellemesini tespit etmez. Eski şemalı çıktıları yeniden kullanmak yerine yeni klasörde üretin.

**Şema geçişi:** Confluence çıktıları görsel gruplamasıyla birlikte v3 oldu. v1/v2 çıktılar `--resume` ile sessizce yeniden kullanılmaz; komut yeni `--output` ister. Örneğin eski `exports_confluence_all` yerine `--output exports_confluence_all_v3` ile tekrar çalıştırın. Önceki dosyalar otomatik dönüştürülmez veya silinmez.

### 7.3. Confluence diyagramları

Doğrudan eklerde `.drawio` uzantısı veya `<mxfile>` / `<mxGraphModel>` kaynağı tanınırsa otomatik analiz yapılır; OCR/vision seçeneği gerekmez. Sıkıştırılmış/sıkıştırılmamış XML, çoklu diyagram sayfası ve object/UserObject düğümleri desteklenir.

Düğüm kimlikleri/etiketleri, bağlantı uçları/etiketleri ve belirtilmiş ok stilleri JSON'a yazılır; okunabilir yapı Markdown'a eklenir. `source` ve `target` bağlantı uçlarıdır; ok stili belirtilmemişse akış yönü uydurulmaz.

PlantUML/Mermaid makrolarında `plain-text-body` varsa kaynak kod korunur. Diğer makrolar tam çözümlenemeyebilir; uyarı ve orijinal storage saklanır. draw.io makrosu ile kaynak ek birebir eşlenmediğinden başarılı analiz yanında makro uyarısı da görülebilir. Gliffy/eklentiye özel depoda erişilebilir raster önizleme veya kaynak yoksa ayrıca adaptör gerekir.

### 7.4. Diğer sınırlar

- Güncel sayfalar ve doğrudan ekler alınır; bloglar, yorumlar, sürüm geçmişi, taslak ve çöp kutusu kapsam dışıdır.
- ACL çıkarılmaz: `acl_status=not_collected`. Çok kullanıcılı arama/RAG için erişim denetimi ayrıca gerekir.
- Başka sayfadan görsel referansları, Confluence iç bağlantıları ve include makroları henüz tam çözülmez.
- PDF/Office ekleri indirilebilir; iç metin/görselleri bu sürümde analiz edilmez.
- Karmaşık tablo/eklenti makrolarında birebir görünüm garanti edilmez; ham kaynak korunur.
- Sayfa sürümü kontrol edilir; bütün site ve ekler için tek transaction/snapshot garantisi yoktur.
- Görsel-açıklama ilişkileri storage yapısına bağlıdır; komşu paragraf eşleştirmesi tahminidir. Eklentiye özel caption/görsel yapıları için adaptör gerekebilir.

## 8. Dosyaların görevleri

| Dosya | Görevi |
| --- | --- |
| `manage.py` | Django komutlarını başlatır |
| `config/settings.py` | Minimal Django ayarları ve proje kökündeki `.env` yüklemesi |
| `.env.example` / `requirements.txt` | Örnek ayarlar / Python bağımlılıkları |
| `exporter/management/commands/export_web.py` | URL, seçici ve analiz seçeneklerini alır |
| `exporter/web_client.py` | Ayrı web HTTP oturumu, yönlendirme ve boyut sınırları |
| `exporter/web.py` | HTML dönüşümü, görsel/açıklama grupları ve web çıktıları |
| `exporter/management/commands/check_confluence.py` | PAT ve API erişimini kontrol eder |
| `exporter/management/commands/export_page.py` | Tek Confluence sayfası aktarımı |
| `exporter/management/commands/export_confluence.py` | Space/ağaç/toplu tarama seçenekleri |
| `exporter/client.py` | Confluence SDK/PAT oturumu, sayfalama ve ek indirme |
| `exporter/crawler.py` | Space keşfi, ağaç dolaşımı ve koşu raporları |
| `exporter/service.py` | Confluence sayfa/eklerini sürüm klasörlerine kaydetme |
| `exporter/parser.py` | Confluence storage biçimini Markdown'a çevirme |
| `exporter/confluence_media.py` | Confluence görsel kullanımlarını, açıklamaları ve bağlamlı analizleri gruplama |
| `exporter/enrichment.py` | Ortak OCR, draw.io kaynak analizi ve yerel Ollama vision |
| `examples/web_demo.html` | Confluence gerektirmeyen örnek sayfa |
| `exporter/tests.py`, `exporter/test_bulk.py`, `exporter/test_web.py`, `exporter/test_confluence_media.py` | İstemci, dönüşüm, tarama ve iki kaynağın gruplama testleri |

Ortak analiz modülü bulunması, iki dönüştürücünün ve JSON çıktılarının bütün davranışlarının aynı olduğu anlamına gelmez.

## 9. Testler ve sonraki RAG aşaması

### 9.1. Testleri çalıştırma

```bash
python manage.py check
python -m unittest exporter.tests exporter.test_bulk exporter.test_web exporter.test_confluence_media -v
```

Mevcut sürümde **53 test** bulunur: 19 Confluence/ortak analiz testi, 20 web testi ve 14 Confluence gruplama testi. SDK/PAT, sayfalama, hata sonrası devam, resume, draw.io, kaynak/kod korunması, görsel-açıklama grupları, URL/charset, indirme sınırları ve gerçek yerel HTTP üzerinden web komutu kapsanır. Yeni testler ayrıca ac:caption/ac:title, aynı ekin farklı bağlamları, eksik/başka sayfaya ait görseller, ağaç taramasında gruplama ve eski şemada resume reddini doğrular.

Gerçek İngilizce Tesseract testi için motor ve `eng` paketi gerekir. Ollama yanıtları taklit edilir; gerçek model çağrılmaz. Şirket Confluence 8.5.3 bağlantısı ve gerçek görsel model bu testlerle doğrulanmış sayılmaz. Türkçe OCR kendi ortamınızda ayrıca kontrol edilmelidir.

### 9.2. Şu anda bir model eğitiliyor mu?

**Hayır. Mevcut aşama veri toplama, dönüştürme ve isteğe bağlı görsel analizidir.** `--vision`, kurulu modelden açıklama alır; modeli bu verilerle eğitmez. Markdown/JSON üretmek tek başına chatbot veya RAG kurulumu değildir.

Sonraki aşama için henüz eklenmemiş parçalar:

1. İki kaynağın çıktılarını okuyacak ortak veri modeli/yükleyici.
2. Sayfa/bölüm ve görsel-açıklama sınırlarını koruyacak parçalama (chunking).
3. Embedding üretimi ve vektör indeksine kayıt.
4. Soruyla ilgili içeriği getirip kaynak gösteren yanıt üretimi.
5. Confluence izinleri, güncellemeler ve silinmeler için erişim/senkronizasyon mekanizması.

Her iki kaynakta `media_groups` sınırları korunmalıdır; sabit karakter sayısıyla bölmek açıklamayı görselden yeniden koparabilir. Orijinal içerik, OCR metni ve model yorumu birbirinden ayırt edilmelidir.

### 9.3. Teknik başvuru kaynakları

- [Confluence Server/Data Center REST API örnekleri](https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/)
- [Confluence storage formatı ve görsel alanları](https://confluence.atlassian.com/doc/confluence-storage-format-790796544.html)
- [atlassian-python-api](https://atlassian-python-api.readthedocs.io/)
- [Tesseract kurulumu](https://tesseract-ocr.github.io/tessdoc/Installation.html)
- [Ollama chat API](https://docs.ollama.com/api/chat)
- [draw.io diyagram kaynakları](https://www.drawio.com/docs/manual/advanced/diagram-source-edit/)

## 10. Komut başvurusu: bütün komutlar ve seçenekler

Bu bölüm README'de kullanılan proje, kurulum ve yardımcı komutları tek yerde toplar. `URL`, `SAYFA_ID`, `SPACE_KEY`, `DIZIN` ve `MODEL_ADI` yer tutucudur; gerçek değerlerle değiştirin. `manage.py` komutlarını proje kökünde, sanal ortam etkin halde çalıştırın. URL'leri tırnak içinde tutun.

### 10.1. Projeyi indirme ve ortamı hazırlama

| Komut | Açıklama / ne zaman kullanılır? |
| --- | --- |
| `git clone https://github.com/Erdeminsan/ai-chatbot-personal.git` | İlk kurulumda projeyi indirir |
| `cd ai-chatbot-personal` | Proje köküne geçer |
| `python3 -m venv venv` | macOS/Linux'ta sanal ortam oluşturur; ilk kurulumda |
| `py -m venv venv` | Windows Python launcher ile sanal ortam oluşturur |
| `source venv/bin/activate` | macOS/Linux'ta mevcut sanal ortamı etkinleştirir |
| `.\venv\Scripts\Activate.ps1` | Windows PowerShell'de mevcut ortamı etkinleştirir |
| `python -m pip install -r requirements.txt` | Etkin Python ortamına proje bağımlılıklarını kurar |
| `cp .env.example .env` | macOS/Linux'ta örnek ayarları kopyalar; yalnızca `.env` yoksa |
| `Copy-Item .env.example .env` | Aynı kopyalama işleminin PowerShell karşılığı; mevcut dosyanın üzerine yazmayın |
| `deactivate` | Etkin sanal ortamdan çıkar; sonraki oturumda yeniden etkinleştirilebilir |

### 10.2. Proje komutları: hızlı seçim

| Komut | Ne yapar? | Gereksinim / varsayılan çıktı |
| --- | --- | --- |
| `python manage.py export_web --url "URL"` | Tek web sayfasını alır; görsel-açıklama grupları oluşturur | PAT gerekmez; `exports_web/` altında yeni klasör |
| `python manage.py check_confluence` | PAT, mevcut kullanıcı ve space API erişimini kontrol eder | Confluence kök adresi ve PAT; dosya üretmez |
| `python manage.py export_page --page-id SAYFA_ID` | Tek Confluence sayfasını ve doğrudan eklerini alır | Confluence erişimi; `exports/<id>/<sürüm>/` |
| `python manage.py export_confluence --root-page-id SAYFA_ID` | Sayfa ve bütün alt sayfalarını alır | Confluence erişimi; `exports_batch/<zaman>/` |
| `python manage.py export_confluence --space-key SPACE_KEY` | Bir space'in her derinlikteki güncel sayfalarını alır | Confluence erişimi; `exports_batch/<zaman>/` |
| `python manage.py export_confluence --all-spaces` | Hesabın görebildiği güncel space'lerdeki güncel sayfaları alır | Confluence erişimi; `exports_batch/<zaman>/` |
| `python manage.py check` | Django ayarlarının sistem kontrolünü yapar | Confluence/Ollama bağlantısını veya analiz kalitesini test etmez |

Gruplama için ayrıca bir komut veya bayrak gerekmez: web ve Confluence aktarımında otomatik uygulanır. OCR ve model yorumu ayrıca etkinleştirilir.

### 10.3. Komut seçeneklerinin tam listesi

Buradaki tablo projede tanımlanan bütün veri aktarım seçeneklerini kapsar. Django'nun genel yardım/hata ayıklama seçenekleri bir sonraki bölümde yer alır.

| Seçenek | Hangi komutlarda? | Varsayılan / zorunluluk | Açıklama |
| --- | --- | --- | --- |
| `--url "URL"` | `export_web` | Zorunlu | Tek HTML sayfasının HTTP/HTTPS adresi |
| `--selector "CSS"` | `export_web` | Otomatik içerik seçimi | Örneğin `#content`; eşleşen ilk alan işlenir |
| `--page-id SAYFA_ID` | `export_page` | Zorunlu | Sayısal Confluence sayfa kimliği |
| `--root-page-id SAYFA_ID` | `export_confluence` | Üç kapsam seçeneğinden biri | Seçilen sayfa ve alt sayfalar |
| `--space-key SPACE_KEY` | `export_confluence` | Üç kapsam seçeneğinden biri | Bir space'in güncel sayfaları |
| `--all-spaces` | `export_confluence` | Üç kapsam seçeneğinden biri | Görünür tüm güncel space'lerin sayfaları |
| `--include-archived-spaces` | `export_confluence` | Kapalı | `--all-spaces` keşfine arşiv space'leri de ekler; güncel sayfa filtresi devam eder |
| `--output DIZIN` | Üç aktarım komutu | Komuta göre yukarıdaki dizinler | Çıktı ana dizinini belirler; dosya adı değildir |
| `--ocr` | Üç aktarım komutu | Kapalı | Raster görsellerin yazılarını çıkarır; Tesseract gerekir |
| `--ocr-lang tur+eng` | Üç aktarım komutu | `tur+eng` | OCR dil paketleri; yalnızca `--ocr` ile etkili |
| `--vision` | Üç aktarım komutu | Kapalı | Raster görsel ve açıklama bağlamını yerel Ollama modeline gönderir |
| `--resume` | `export_page`, `export_confluence` | Kapalı | Aynı kaynak/sürüm/ayarlarla uyarısız v3 çıktı varsa yeniden kullanır; web komutunda yoktur |

`export_confluence` içinde `--all-spaces`, `--space-key` ve `--root-page-id` seçeneklerinden tam birini verin. Toplu `--resume` için önceki `--output` zorunludur. Eski Confluence şeması veya farklı analiz ayarları için yeni çıktı dizini kullanın. `check_confluence` özel bir seçenek gerektirmez; ayarları `.env` dosyasından okur.

### 10.4. Yardım ve hata ayıklama

| Komut/seçenek | Açıklama |
| --- | --- |
| `python manage.py help` | Django ve proje komutlarını listeler; her listelenen komutun bu projede gerekli olduğu anlamına gelmez |
| `python manage.py export_web --help` | Web komutunun seçenekleri |
| `python manage.py export_page --help` | Tek sayfa komutunun seçenekleri |
| `python manage.py export_confluence --help` | Toplu tarama seçenekleri |
| `python manage.py check_confluence --help` | Bağlantı kontrolü ve genel seçenekler |
| `--traceback` | Hatalarda Python traceback gösterir; örneğin `python manage.py export_page --page-id 123456 --traceback` |
| `-v 0`, `-v 1`, `-v 2`, `-v 3` / `--verbosity` | Django ayrıntı seviyesi, varsayılan 1; proje ilerleme mesajlarının tamamı bu ayara göre filtrelenmez |
| `--no-color` / `--force-color` | Terminal renklerini kapatır/zorlar; birlikte kullanılmaz |
| `--settings config.settings` | Django ayar modülünü belirtir; proje zaten bunu varsayar |
| `--pythonpath DIZIN` | Ek Python import yolu sağlar; normal kullanımda gerekmez |
| `--skip-checks` | Destekleyen komutlarda Django başlangıç sistem kontrollerini atlar; bağlantı/analiz doğrulaması sağlamaz |
| `--version` | Django sürümünü gösterir; projenin veya JSON şemasının sürümü değildir |

### 10.5. Yerel örnek, OCR ve model komutları

| Komut | Açıklama |
| --- | --- |
| `python -m http.server 8000 --bind 127.0.0.1 --directory examples` | Örnek HTML'i yalnızca yerel arayüzde yayınlar; terminal açık kalır |
| `python manage.py export_web --url "http://127.0.0.1:8000/web_demo.html" --output exports_demo` | İkinci terminalden yerel örneği aktarır |
| `brew install tesseract tesseract-lang` | macOS/Homebrew için OCR motoru ve dil paketleri |
| `sudo apt install tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng` | Debian/Ubuntu için OCR kurulumu; Red Hat komutu değildir |
| `tesseract --list-langs` | Kurulu OCR dillerini gösterir; `tur+eng` için ikisi de gerekir |
| `ollama pull MODEL_ADI` | Seçilen modeli indirir; görsel girdisi destekleyen model seçin |
| `ollama list` | Kurulu modelleri ve tam adlarını gösterir |
| `ollama serve` | Gerektiğinde yerel Ollama sunucusunu başlatır; zaten çalışıyorsa ikinci kez başlatmayın |
| `Ctrl+C` | Terminaldeki örnek sunucuyu/komutu durdurur; Confluence toplu tarama tamamlanan sayfaları ve özeti korur |

### 10.6. Sık kullanılan birleşimler

```bash
# Web: belirli içerik alanı + OCR + görsel yorumu
python manage.py export_web --url "https://ornek.com/dokuman" --selector "#content" --ocr --ocr-lang tur+eng --vision --output exports_web_vision

# Confluence: tek sayfa + görsel açıklamalarıyla bağlamlı analiz
python manage.py export_page --page-id 123456 --ocr --ocr-lang tur+eng --vision --output exports_confluence_v3

# Confluence: tek space + aynı analizler
python manage.py export_confluence --space-key ENG --ocr --ocr-lang tur+eng --vision --output exports_eng_v3

# Önceki v3 toplu çıktıyla aynı OCR/model ayarlarını kullanarak devam et
python manage.py export_confluence --space-key ENG --ocr --ocr-lang tur+eng --vision --output exports_eng_v3 --resume
```

### 10.7. Doğrulama komutları

| Komut | Açıklama |
| --- | --- |
| `python manage.py check` | Django sistem kontrolü |
| `python -m unittest exporter.tests exporter.test_bulk exporter.test_web exporter.test_confluence_media -v` | Bütün proje testleri; gerçek İngilizce OCR testi için Tesseract/eng gerekir |
| `python -m unittest exporter.test_confluence_media -v` | Yalnızca Confluence gruplama, bağlamlı analiz ve şema geçişi testleri |
| `python -m unittest exporter.test_web -v` | Yalnızca web aktarım testleri |
