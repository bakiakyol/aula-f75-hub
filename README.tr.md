<div align="center">

# aula-f75-hub

**AULA F75 klavye için ışık efektleri, tuş başı RGB ve tuş atama. Linux'ta, üretici yazılımı olmadan.**

[English](README.md) · **Türkçe**

[![tests](https://github.com/OWNER/aula-f75-hub/actions/workflows/tests.yml/badge.svg)](https://github.com/OWNER/aula-f75-hub/actions/workflows/tests.yml)
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
- **Tuş başı RGB**: Çizimde tuşlara tıklayıp boya. Hazır temalar da var.
- **Tuş atama**: Normal ve Fn katmanında. Her değişiklik klavyeden geri okunup doğrulanıyor.
- **Cihaz ayarları**: Yan gösterge, tekerlek modu (ses ya da ışık), işletim sistemi
  modu (Windows / Android / Mac), Windows tuşu kilidi.
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

| Klavye | Bağlantı | Durum |
|---|---|---|
| AULA F75 | 2.4G dongle (`3554:fa09`) | ✅ Doğrulandı |
| AULA F75 | Bluetooth (`3554:fa07`) | ⚠️ Aynı kanal, henüz denenmedi |
| AULA F75 | Kablo (`258a:010c`) | ❌ Henüz desteklenmiyor (farklı iletim katmanı) |
| Diğer AULA modelleri | – | ❓ Bilinmiyor. Lütfen [bildir](../../issues/new/choose) |

## Kurulum

```bash
git clone https://github.com/OWNER/aula-f75-hub.git
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
aula side-light breathing                  # off | fill | breathing | static
aula knob lighting                         # media | lighting
aula os mac                                # windows | android | mac
aula win-lock on
aula backup ~/aula-yedek
aula restore ~/aula-yedek
```

Türkçe Q klavyede `ğ ü ş ö ç ı` harfleri de tuş adı olarak kullanılabilir, örneğin
`aula key-color ğ=ff0000 ş=00ff00`.

Renk adları: `red` (kırmızı), `green` (yeşil), `blue` (mavi), `yellow` (sarı),
`purple` (mor), `cyan` (camgöbeği), `white` (beyaz), `multi` (gökkuşağı).

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
| `the keyboard didn't answer` | Klavye uyuyor. Bir tuşa bas ve tekrar dene |
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
- [ ] Bluetooth'un doğrulanması
- [ ] Makrolar
- [ ] Daha fazla tema

## Katkı

Hata ve cihaz bildirimlerine her zaman açığız. Türkçe de yazabilirsin.
Ayrıntılar: [CONTRIBUTING.md](CONTRIBUTING.md).

## Sorumluluk reddi

Bu bağımsız bir projedir. AULA ile bir bağı yoktur, AULA tarafından onaylanmamış ya
da desteklenmemiştir. "AULA" adı sadece aracın çalıştığı donanımı belirtmek için
kullanılmıştır. Kullanım sorumluluğu kullanıcıya aittir.

## Lisans

[MIT](LICENSE) © 2026 Baki Akyol
