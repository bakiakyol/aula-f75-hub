# aula-f75-hub

[English](README.md) | **Türkçe**

**AULA F75** klavye için Linux ayar aracı: ışık efektleri, tuş başı RGB, tuş atama ve
yedekleme. Resmi yazılım sadece Windows'ta çalışıyor (ve ışık ayarları orada da bozuk).
Bu araç klavyenin protokolünü doğrudan kullanıyor ve ek bir kütüphane gerektirmiyor.

Durum: **2.4G dongle** ile çalıştığı doğrulandı. Bluetooth aynı kanalı kullanıyor
(denenmedi). Kablolu mod henüz desteklenmiyor.

## Kurulum

Klavyeye sudo'suz erişebilmek için udev kuralını kur. Bu sadece bir kere yapılıyor:

```bash
sudo cp udev/70-aula-f75.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Kullanım

```bash
./aula.sh devices                         # klavyeyi bul
./aula.sh info                            # şu anki efekt / parlaklık / hız / renk
./aula.sh effects                         # efekt ve renk listesi
./aula.sh effect static -c red -b 9       # efekti değiştir (-c renk, -b parlaklık 0-9, -s hız 0-4)
./aula.sh brightness 5
./aula.sh side-light breathing            # Esc yanındaki beyaz çubuk: off | fill | breathing | static
./aula.sh knob lighting                   # tekerlek: media (ses, sessiz) | lighting (parlaklık, efekt)
./aula.sh os mac                          # işletim sistemi modu: windows | android | mac
./aula.sh win-lock on                     # Windows tuşunu kilitle
./aula.sh keys                            # tuş adları
./aula.sh key-color esc=ff0000 w=00ff00   # tek tek tuş rengi (özel efekte geçer)
./aula.sh key-color --clear all=0010ff w=ff0000 a=ff0000 s=ff0000 d=ff0000
./aula.sh preset synthwave                # hazır renk temasını yükle (isimsiz: listele)
./aula.sh remap capslock lctrl            # CapsLock -> Ctrl  (geri al: remap capslock capslock)
./aula.sh remap f1 esc -l 1               # Fn katmanına (katman 1) atama
./aula.sh backup ~/aula-yedek
./aula.sh restore ~/aula-yedek
```

Türkçe Q klavyede `ğ ü ş ö ç ı` harfleri doğrudan tuş adı olarak yazılabilir, ör.
`./aula.sh key-color ğ=ff0000 ş=00ff00`.

Renk adları: `red` (kırmızı), `green` (yeşil), `blue` (mavi), `yellow` (sarı),
`purple` (mor), `cyan` (camgöbeği), `white` (beyaz), `multi` (gökkuşağı).

`backup/` klasöründe, bu araç klavyeye hiçbir şey yazmadan önce okunmuş orijinal
ayarlar duruyor. Bir şeyler ters giderse: `./aula.sh restore backup`

## Testler

```bash
python3 -m unittest -v
```

Protokol ayrıntıları (İngilizce): [docs/protocol.md](docs/protocol.md)
