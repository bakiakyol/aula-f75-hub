<div align="center">

# aula-f75-hub

**AULA F75 klavye için ışık efektleri, tuş başı RGB ve tuş atama. Linux'ta, üretici yazılımı olmadan.**

[English](README.md) · **Türkçe**

[![tests](https://github.com/bakiakyol/aula-f75-hub/actions/workflows/tests.yml/badge.svg)](https://github.com/bakiakyol/aula-f75-hub/actions/workflows/tests.yml)
![lisans](https://img.shields.io/badge/lisans-MIT-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![platform](https://img.shields.io/badge/platform-Linux-informational)

<img src="docs/screenshots/main.png" alt="Ana pencere: klavye gerçek tuş renkleriyle çizilmiş, boyamak için üç tuş seçili" width="820">

</div>

AULA'nın resmi yazılımı sadece Windows'ta çalışıyor. Denendiği bilgisayarda ışık
ayarları orada bile çalışmadı. Bu proje klavyeyle doğrudan, HID ayar kanalı
üzerinden konuşuyor. Protokol, resmi uygulamanın kodu (çalıştırılmadan) okunarak
çıkarıldı ve her bulgu gerçek bir klavyede tek tek doğrulandı.

## Özellikler

- **15 ışık efekti**, renk, parlaklık ve hız ayarıyla: nefes, yağmur damlası, yılan,
  şelale, gökkuşağı çarkı, tuşa basınca yayılan dalgalar…
- **Tuş başı RGB**: Çizimde tuşlara tıklayıp boya. 9 hazır tema da var.
- **Tuş atama**: Normal ve Fn katmanında. Her değişiklik klavyeden geri okunup doğrulanıyor.
- **Makrolar**: Tuş kombinasyonları, yazı ve beklemeler. Bir kez, N kez, basılı
  tutulduğu sürece ya da başka bir tuşa basılana kadar çalıştırılabiliyor. Adımlar
  yazılabiliyor ya da klavyeden kaydedilebiliyor. Yazılar klavye düzenine (ABD ya da
  Türkçe Q) göre çıkıyor.
- **Cihaz ayarları**: Yan gösterge, tekerlek modu (ses ya da ışık), işletim sistemi
  modu (Windows / Android / Mac), Windows tuşu kilidi, uyku süresi.
- **Pil yüzdesi** (deneysel) ve bağlantı türü üst çubukta.
- **Yedekleme ve geri yükleme**, klavyenin fabrika ayarları dahil.
- **Canlı önizleme**: Çalışan efektin klavyede kabaca nasıl göründüğünü gösteriyor.
- Betiklerde kullanmak için tam bir **komut satırı aracı** ve GTK 3 arayüzü.
- Python dışında bağımlılık yok. Arayüz GTK 3 kullanıyor, çoğu masaüstünde hazır geliyor.

<table>
<tr>
<td><img src="docs/screenshots/rainbow.png" alt="Gökkuşağı çarkı efektinin çizimdeki önizlemesi" width="400"></td>
<td><img src="docs/screenshots/remap.png" alt="CapsLock seçili tuş atama sayfası" width="400"></td>
</tr>
<tr>
<td align="center">Canlı efekt önizlemesi</td>
<td align="center">Tuş atama</td>
</tr>
</table>

## Desteklenen donanım

Bağlantı türü klavyenin arkasındaki anahtarla seçiliyor (2.4G / kablo / Bluetooth).
Araç hangisi aktifse onu kendisi buluyor.

| Klavye | Bağlantı | Durum |
|---|---|---|
| AULA F75 | 2.4G dongle (`3554:fa09`) | ✅ Doğrulandı |
| AULA F75 | Bluetooth (`3554:fa07`) | ✅ Doğrulandı |
| AULA F75 | Kablo (`258a:010c`) | ❌ Henüz desteklenmiyor (farklı iletim katmanı) |
| Diğer AULA modelleri | – | ❓ Bilinmiyor. Lütfen [bildir](../../issues/new/choose) |

## Kurulum

```bash
git clone https://github.com/bakiakyol/aula-f75-hub.git
cd aula-f75-hub
./install.sh
```

`install.sh` klavyenin `sudo` olmadan kullanılabilmesi için bir udev kuralı kurar,
`~/.local/bin` içine bir `aula` komutu koyar ve uygulama menüsüne **AULA F75**
kısayolunu ekler. `./install.sh --remove` hepsini geri alır.

Arayüz Python için GTK 3 gerektirir. Linux Mint ve Ubuntu'da zaten kurulu geliyor.
Diğer dağıtımlarda `python3-gi` ve `gir1.2-gtk-3.0` paketlerini (ya da dağıtımındaki
karşılıklarını) kur. Komut satırı aracı için Python 3.10+ dışında bir şey gerekmez.

## Kullanım

### Grafik arayüz

```bash
aula gui
```

Bir tuşa tıklayıp seç (**Ctrl+tık** ile birden fazla), sonra klavyenin altından bir
renk seç. Soldaki sayfalardan efekti değiştirebilir, tuş atayabilir, yan göstergeyi,
tekerleği ve işletim sistemi modunu ayarlayabilir, yedek alabilirsin.

### Komut satırı

```bash
aula info                                  # efekt, parlaklık, pil, yan gösterge, tekerlek…
aula effects                               # efekt ve renk listesi
aula effect breathing -c blue -b 9 -s 2    # -c renk, -b parlaklık 0-9, -s hız 0-4
aula key-color --clear all=0010ff w=ff0000 a=ff0000 s=ff0000 d=ff0000
aula preset synthwave                      # hazır tuş renk teması
aula remap capslock lctrl                  # geri al: aula remap capslock capslock
aula remap f1 esc -l 1                     # Fn katmanına atama
aula macro set selam "text:merhaba" --key y -l 1        # Fn+Y "merhaba" yazar
aula macro set yapistir "ctrl+c" "wait:100" "ctrl+v" --key f1 --repeat 2
aula macro list                            # kayıtlı makrolar ve atandıkları tuşlar
aula macro delete selam                    # tuşu fabrika işlevine döner
aula side-light breathing                  # off | fill | breathing | static
aula knob lighting                         # media | lighting
aula os mac                                # windows | android | mac
aula win-lock on
aula sleep 10m                             # 10 dk boşta kalınca uyu (30 sn adımlarla 20m'ye kadar, ya da off)
aula backup ~/aula-yedek
aula restore ~/aula-yedek
```

Türkçe Q klavyede `ğ ü ş ö ç ı` harfleri de tuş adı olarak kullanılabilir, örneğin
`aula key-color ğ=ff0000 ş=00ff00`.

Renk adları: `red` (kırmızı), `green` (yeşil), `blue` (mavi), `yellow` (sarı),
`purple` (mor), `cyan` (camgöbeği), `white` (beyaz), `multi` (gökkuşağı).

### Temalar

`aula preset AD` bütün tuşları tek seferde boyar (arayüzde Lighting sayfasından da
seçilebilir). Sadece `aula preset` yazarsan temaları listeler.

| Tema | Renkler |
|---|---|
| `synthwave` | mor → pembe → camgöbeği, beyaz WASD/ok tuşları, turuncu Esc |
| `cyberpunk` | neon sarı → canlı pembe → camgöbeği, beyaz WASD/ok tuşları, kırmızı Esc |
| `dracula` | koyu mor → pembe → camgöbeği, sarı WASD, yeşil Esc |
| `matrix` | koyu yeşil → parlak yeşil → koyu yeşil, kırmızı Esc |
| `sunset` | koyu mor → turuncu → sarı, beyaz WASD |
| `volcano` | koyu kırmızı → parlak turuncu → sarı, camgöbeği WASD/Esc |
| `aurora` | lacivert → kutup ışığı yeşili → mor, canlı pembe WASD |
| `miami-vice` | parlak camgöbeği → canlı pembe → mor, sarı WASD |
| `toxic` | koyu gri → asit yeşili → koyu gri, mor WASD |

### Makrolar

Makro, bir tuşa basınca klavyenin kendi kendine oynattığı adımlar listesidir.
Klavyenin içinde saklanır. Bu yüzden her programda, bilgisayar yeniden başladıktan
sonra ve başka bilgisayarlarda da çalışır.

**Arayüzde** **Macros** sayfasını aç:

1. **New macro…** seç, bir ad ver ve adımları her satıra bir tane gelecek şekilde yaz.
2. **Save macro**'ya bas.
3. Çizimde makroyu çalıştıracak tuşa tıkla, katmanı seç (**Fn layer** = Fn + o tuş)
   ve kaç kez tekrarlanacağını ayarla.
4. **Assign to selected key**'e bas.

Adımları yazmak yerine **kaydedebilirsin**: **⏺ Record**'a bas, klavyede yaz, sonra
**⏹ Stop**'a tıkla. Basılan tuşlar adımlara dönüşür (yazılan karakterler `text:`
adımına, kısayollar `ctrl+a` gibi kombinasyonlara). Kaydetmeden önce bunları kontrol
edip düzeltebilirsin. **Keep pauses** işaretliyse 100 ms ve üstü duraklamalar `wait:`
adımı olarak korunur. Adı kayda başlamadan önce yaz, çünkü kayıt sırasında basılan her
tuş kayda gider. Masaüstünün kendisinin yakaladığı kısayollar (Alt+Tab, Win tuşu) ve
burada adı olmayan tuşlar (ses, tekerlek) kaydedilmez.

Kayıtlı bir makroyu seçince olayları yorum satırı olarak görünür. Değiştirmek için
altına yeni adımları yazıp aynı adla kaydet.

**Komut satırında** `aula macro set` makroyu kaydeder, `--key` verilirse tuşa da atar:

```bash
aula macro set AD ADIM [ADIM …] [--key TUŞ] [-l KATMAN] [--repeat N | --while-held | --until-key]
aula macro assign TUŞ AD [-l KATMAN]       # kayıtlı makroyu başka bir tuşa ata
```

#### Adımlar

| Adım | Ne yapar | Örnekler |
|---|---|---|
| `text:…` | yazıyı yazar | `text:Merhaba dünya!` |
| tuş ya da kombinasyon | tuşlara birlikte basıp bırakır | `enter` · `f5` · `ctrl+c` · `ctrl+shift+t` · `alt+tab` · `win` |
| `wait:MS` | sonraki adımdan önce MS milisaniye bekler (ilk adım olamaz) | `wait:500` |
| `down:TUŞ` / `up:TUŞ` | tek bir tuşa basar ya da bırakır; başka adımlar boyunca basılı kalacak tuşlar için | `down:shift` · `up:shift` |

- **Tuş adları:** `a`–`z`, `0`–`9`, `f1`–`f12`, `enter`, `esc`, `tab`, `space`,
  `backspace`, `delete`, `insert`, `home`, `end`, `pgup`, `pgdn`, `up`, `down`,
  `left`, `right`, `printscreen`, `capslock`, `menu` ve işaret tuşları (`minus`,
  `comma`, `slash`…). Türkçe Q'da `ğ ü ş ö ç ı` de olur (ör. `ctrl+ş`).
  Tam liste `aula keys` çıktısının sonunda.
- **Değiştirici tuşlar:** `ctrl`, `shift`, `alt`, `win` (ya da `super`), `altgr`.
  Tek taraf için: `lctrl`, `rctrl`, `lshift`, `rshift`, `lalt`, `ralt`, `lwin`, `rwin`.
- Olaylar arasında 20 ms var. Bir adımdan sonra daha uzun beklemek için `wait:`,
  bütün makronun hızını değiştirmek için `--delay MS` kullan.
- Fare tuşları ve medya tuşları (ses, oynat) şimdilik adımlarda kullanılamıyor.

#### Yazı ve klavye düzeni

Klavye sadece tuşun konumunu gönderir, o tuştan hangi karakterin çıkacağına
bilgisayardaki klavye düzeni karar verir. Bu yüzden `text:` adımları, **senin**
düzeninde o karakterleri veren tuşlarla yazılır. Düzen otomatik algılanır
(`setxkbmap`, o yoksa `/etc/default/keyboard`).

| Düzen | `text:` neleri yazabilir |
|---|---|
| `us` (İngilizce ABD) | ASCII: harfler, rakamlar, boşluk, noktalama, Enter (`\n`), Tab |
| `tr` (Türkçe Q) | bunlara ek olarak `ı İ ğ ü ş ö ç Ğ Ü Ş Ö Ç` ve AltGr karakterleri `@ € ₺ { } [ ] \ \| ~ < >` |

Algılanan düzeni değiştirmek için `--layout us` / `--layout tr` ya da arayüzdeki
**Text layout** kutusunu kullan. Makro, kaydedildiği düzene göre yazılır; düzeni farklı
bir bilgisayarda yazısı farklı çıkar. Başka düzenlerde `us` seç ve ABD klavyesindekiyle
aynı yerde duran harf ve rakamları kullan.

#### Tekrar modları

| Arayüz | Komut satırı | Ne olur |
|---|---|---|
| Run N times | `--repeat N` (varsayılan 1) | makroyu N kez oynatır (1-255) |
| Repeat while held | `--while-held` | tuş basılı durdukça tekrarlar |
| Repeat until a key is pressed | `--until-key` | herhangi bir tuşa basana kadar tekrarlar |

#### Bellek

Klavyedeki bütün makrolar, fabrika makrosu `M1` dahil, toplam **512 bayt** paylaşır.

- Her tuş vuruşu 8 bayt tutar. Shift ya da AltGr gereken bir karakter 16 bayt tutar.
- Her makro ayrıca 5 bayt ve adının her harfi için 2 bayt kaplar (ad en fazla 30 harf).

Bu, toplamda yaklaşık 55 küçük harflik yazı demek. Makrolar uzun paragraflar için
değil, kısayollar ve kısa ifadeler için. Sığmayan makro kaydedilmez, bir hata mesajı
çıkar ve klavyede hiçbir şey değişmez.

#### Silme

`aula macro delete AD` (ya da arayüzde **Delete macro**) makroyu siler. O makroyu
çalıştıran tuşlar fabrika işlevlerine döner.

#### Örnekler

```bash
# Fn+F1 uygulama menüsünden Firefox'u açar
aula macro set firefox "win" "wait:400" "text:firefox" "wait:300" "enter" --key f1 -l 1

# Fn+S iki satırlık bir imza yazar
aula macro set imza "text:Saygılarımla," "enter" "text:Ali" --key s -l 1

# Fn+D çoğu editörde satırı çoğaltır: Home, Shift+End, kopyala, End, Enter, yapıştır
aula macro set cogalt "home" "shift+end" "ctrl+c" "end" "enter" "ctrl+v" --key d -l 1

# Oyunlar için: Fn+Space basılı durdukça Space'e basmaya devam eder
aula macro set spam "space" --key space -l 1 --while-held

# W'yi basılı tutup zıpla, sonra W'yi bırak
aula macro set kosziple "down:w" "wait:200" "space" "wait:300" "up:w" --key w -l 1
```

### Işık efektleri

| No | Efekt | No | Efekt |
|---|---|---|---|
| 1 | static: sabit | 10 | snake: yılan |
| 2 | breathing: nefes | 11 | stream: soldan sağa akış |
| 3 | spectrum: renkli nefes | 12 | reactive: basılan tuş yanar |
| 4 | ripple-row: basılan tuştan satır boyunca yayılır | 13 | center-wave: ortadan iki yana |
| 5 | raindrops: yağmur damlası | 15 | rainbow-wheel: gökkuşağı çarkı |
| 6 | wave: dalga | 16 | waterfall: şelale |
| 7 | ripple: basılan tuştan bütün klavyeye yayılır | 17 | center-flash: ortadan yanıp sönme |
| 8 | twinkle: rastgele tuşlar | 32 | custom: tuş başı renkler |

Resmi uygulamadaki efekt isimleri ve numaraları firmware ile uyuşmuyor. Bu liste,
bütün efekt numaraları klavyede tek tek denenerek çıkarıldı.

## Güvenlik

- `backup/` klasöründe, fabrika ayarlarındaki bir F75'ten bu araç hiçbir şey
  yazmadan önce okunmuş ayarlar duruyor. `aula restore backup` bunları klavyene yükler.
- **Fn + Esc**'ye basılı tutmak klavyeyi fabrika ayarlarına döndürür.
- Araç sadece anlamını bildiği ayar komutlarını gönderir. Firmware'e ve bootloader'a
  asla dokunmaz.

## Sorun giderme

| Mesaj | Çözüm |
|---|---|
| `permission denied` | `./install.sh`'i çalıştır ya da `udev/` içindeki kuralı elle kur |
| `the keyboard didn't answer` | Klavye uyuyor. Bir tuşa bas ve tekrar dene (ne kadar sürede uyuyacağını `aula sleep` ayarlar) |
| `a key seems to be held down` | Klavyeden elini çek. Araç klavyeyle konuşmadan önce bütün tuşların bırakılmasını bekliyor, yoksa kaybolan bir "tuş bırakıldı" sinyali bir tuşun sonsuza kadar tekrar etmesine yol açabiliyor |
| `connected by cable` | 2.4G dongle ya da Bluetooth kullan, kablolu mod henüz desteklenmiyor |

## Nasıl çalışıyor?

Klavye üreticiye özel bir HID kanalını dinliyor (rapor `0x13`, 8 bitlik checksum'lı
20 baytlık paketler) ve her yazmayı aynen geri göndererek onaylıyor. Ayarlar birkaç
blokta tutuluyor: 128 baytlık ışık bloğu, katman başına 504 baytlık tuş haritası ve
378 baytlık tuş başı renk tablosu. Ayrıntılar (İngilizce):
[docs/protocol.md](docs/protocol.md).

## Yol haritası

- [ ] Kablolu mod (aynı veri, farklı iletim katmanı)
- [x] Bluetooth
- [x] Makrolar
- [x] GUI'de klavyeden makro kaydetme
- [x] Daha fazla tema

## Katkı

Hata ve cihaz bildirimlerine her zaman açığız. Türkçe de yazabilirsin.
Ayrıntılar: [CONTRIBUTING.md](CONTRIBUTING.md).

## Sorumluluk reddi

Bu bağımsız bir projedir. AULA ile bir bağı yoktur, AULA tarafından onaylanmamış ya
da desteklenmemiştir. "AULA" adı sadece aracın çalıştığı donanımı belirtmek için
kullanılmıştır. Kullanım sorumluluğu kullanıcıya aittir.

## Lisans

[MIT](LICENSE) © 2026 Baki Akyol
