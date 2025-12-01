import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import google.generativeai as genai
import os

# Sayfa Ayarları
st.set_page_config(
    page_title="Youtekonomi",
    page_icon="favicon.png",
    layout="centered",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "Youtekonomi - YouTube Ekonomi Asistanı"
    }
)

# Başlık ve Açıklama
import yfinance as yf
from datetime import datetime, timedelta, timezone

# ... (Mevcut importlar ve ayarlar) ...

def get_market_data():
    """Anlık piyasa verilerini çeker."""
    try:
        tickers = {
            "USDTRY=X": "Dolar",
            "EURTRY=X": "Euro",
            "XU100.IS": "BIST 100",
            "GC=F": "Ons Altın",
            "BTC-USD": "Bitcoin"
        }
        
        # Son 5 günlük veriyi alıp, eksik verileri (hafta sonu/tatil) önceki günle dolduruyoruz (ffill)
        data = yf.download(list(tickers.keys()), period="5d", interval="1d", progress=False)['Close'].ffill().iloc[-1]
        
        # Gram Altın Hesabı: (Ons * Dolar) / 31.1035
        dolar = data["USDTRY=X"]
        ons = data["GC=F"]
        gram_altin = (ons * dolar) / 31.1035
        
        market_info = {
            "Dolar": f"{dolar:.2f} ₺",
            "Euro": f"{data['EURTRY=X']:.2f} ₺",
            "Gram Altın": f"{gram_altin:.0f} ₺",
            "BIST 100": f"{data['XU100.IS']:.0f}",
            "Bitcoin": f"${data['BTC-USD']:.0f}"
        }
        return market_info
    except Exception as e:
        return None

# ... (Mevcut kodlar) ...

# Ana Arayüz Başlangıcı (Başlık Altına)
st.title("📊 YouTube Ekonomi Özeti Asistanı")

# Tarih ve Piyasa Bilgisi
today_date = datetime.now().strftime("%d.%m.%Y")
market_data = get_market_data()

if market_data:
    # CSS ile şık bir bilgi bandı
    st.markdown(f"""
    <style>
        .market-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            padding: 10px;
            background-color: #f0f2f6;
            border-radius: 10px;
            margin-bottom: 20px;
            justify-content: space-around;
        }}
        .market-item {{
            display: flex;
            flex-direction: column;
            align-items: center;
            background: white;
            padding: 8px 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            min-width: 100px;
        }}
        .market-label {{
            font-size: 0.8em;
            color: #666;
            font-weight: bold;
        }}
        .market-value {{
            font-size: 1.1em;
            color: #333;
            font-weight: bold;
        }}
        /* Dark mode uyumu için */
        @media (prefers-color-scheme: dark) {{
            .market-container {{ background-color: #262730; }}
            .market-item {{ background-color: #0e1117; box-shadow: 0 2px 4px rgba(255,255,255,0.1); }}
            .market-label {{ color: #aaa; }}
            .market-value {{ color: #fff; }}
        }}
    </style>
    
    <div class="market-container">
        <div class="market-item">
            <span class="market-label">📅 Tarih</span>
            <span class="market-value">{today_date}</span>
        </div>
        <div class="market-item">
            <span class="market-label">💵 Dolar</span>
            <span class="market-value">{market_data['Dolar']}</span>
        </div>
        <div class="market-item">
            <span class="market-label">💶 Euro</span>
            <span class="market-value">{market_data['Euro']}</span>
        </div>
        <div class="market-item">
            <span class="market-label">🟡 Gram Altın</span>
            <span class="market-value">{market_data['Gram Altın']}</span>
        </div>
        <div class="market-item">
            <span class="market-label">📈 BIST 100</span>
            <span class="market-value">{market_data['BIST 100']}</span>
        </div>
        <div class="market-item">
            <span class="market-label">🪙 Bitcoin</span>
            <span class="market-value">{market_data['Bitcoin']}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info(f"📅 Tarih: {today_date} | Piyasa verileri alınıyor...")

st.markdown("---")

# ... (Geri kalan kodlar) ...
st.markdown("""
Bu uygulama, izlemeye vaktiniz olmayan uzun ekonomi videolarını sizin için izler ve özetler.
Tek yapmanız gereken videonun linkini yapıştırmak!
""")

# Sidebar - API Anahtarı Girişi
with st.sidebar:
    st.header("⚙️ Ayarlar")
    
    # Önce Secrets'tan (Bulut Kayıtlarından) okumayı dene
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ API Anahtarı Kayıtlı")
    else:
        # Yoksa kullanıcıdan iste
        api_key = st.text_input("Google Gemini API Anahtarı", type="password", help="Google AI Studio'dan alacağınız API anahtarı.")
        st.markdown("[API Anahtarı Nasıl Alınır?](https://aistudio.google.com/app/apikey)")
        st.info("Bu anahtar sadece bu oturumda kullanılır.")

# Fonksiyonlar
def extract_video_id(url):
    """YouTube URL'sinden Video ID'sini çeker."""
    url = url.strip()
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    elif "youtube.com/shorts/" in url:
        return url.split("shorts/")[1].split("?")[0]
    elif "youtube.com/live/" in url:
        return url.split("live/")[1].split("?")[0]
    elif "v=" in url:
        return url.split("v=")[1].split("&")[0]
    return None

import yt_dlp
import requests
import re
import html

def clean_xml_transcript(text):
    """XML/TTML formatındaki altyazıları temizler."""
    # 1. XML taglerini kaldır (<p...>, </p>, <br/> vb.)
    text = re.sub(r'<[^>]+>', ' ', text)
    # 2. HTML entity'lerini çöz (&#39; -> ' gibi)
    text = html.unescape(text)
    # 3. Fazla boşlukları temizle
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_transcript(video_url):
    """Videonun altyazılarını çeker (Hibrit Yöntem: yt-dlp + youtube-transcript-api)."""
    
    # 1. YÖNTEM: yt-dlp (Öncelikli)
    try:
        # User-Agent ekleyerek 429 hatasını azaltmaya çalışalım
        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'skip_download': True,
            'subtitleslangs': ['tr', 'en'],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        }

        # URL düzeltme
        if "youtube.com" not in video_url and "youtu.be" not in video_url:
             video_url = f"https://www.youtube.com/watch?v={video_url}"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            subtitles = info.get('subtitles', {})
            auto_captions = info.get('automatic_captions', {})
            
            selected_sub = None
            if 'tr' in subtitles: selected_sub = subtitles['tr']
            elif 'tr' in auto_captions: selected_sub = auto_captions['tr']
            elif 'en' in subtitles: selected_sub = auto_captions['en'] # Changed to auto_captions for 'en'
            elif 'en' in subtitles: selected_sub = subtitles['en']
            
            if selected_sub:
                sub_url = None
                for fmt in selected_sub:
                    if fmt['ext'] == 'json3':
                        sub_url = fmt['url']
                        break
                if not sub_url: sub_url = selected_sub[-1]['url']

                response = requests.get(sub_url)
                response.raise_for_status()
                
                if 'json3' in sub_url or 'fmt=json3' in sub_url:
                    data = response.json()
                    text_content = ""
                    if 'events' in data:
                        for event in data['events']:
                            if 'segs' in event:
                                for seg in event['segs']:
                                    if 'utf8' in seg:
                                        text_content += seg['utf8'] + " "
                    return clean_xml_transcript(text_content)
    except Exception as e:
        print(f"yt-dlp hatası: {e}")
        # Hata durumunda pass geçip 2. yönteme düşecek
        pass

    # 2. YÖNTEM: youtube-transcript-api (Yedek / Fallback)
    try:
        video_id = extract_video_id(video_url)
        if not video_id:
            return None
            
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Önce Türkçe, yoksa İngilizce, o da yoksa otomatik çeviri
        try:
            transcript = transcript_list.find_transcript(['tr', 'en'])
        except:
            # Bulamazsa herhangi birini alıp Türkçe'ye çevir
            transcript = transcript_list.find_transcript(['en']).translate('tr')
            
        formatter = TextFormatter()
        text_formatted = formatter.format_transcript(transcript.fetch())
        return clean_xml_transcript(text_formatted)

    except Exception as e:
        print(f"youtube-transcript-api hatası: {e}")
        pass

    # 3. YÖNTEM: Invidious API (Genişletilmiş Liste)
    import random
    invidious_instances = [
        "https://inv.tux.pizza",
        "https://invidious.projectsegfau.lt",
        "https://vid.puffyan.us",
        "https://invidious.fdn.fr",
        "https://invidious.drgns.space",
        "https://invidious.perennialteks.com",
        "https://yt.artemislena.eu",
        "https://invidious.flokinet.to",
        "https://invidious.privacydev.net",
        "https://iv.ggtyler.dev",
        "https://invidious.lunar.icu",
        "https://yewtu.be"
    ]
    random.shuffle(invidious_instances) # Her seferinde farklı sırayla dene

    video_id = extract_video_id(video_url)
    if not video_id: return None

    for instance in invidious_instances:
        try:
            # Altyazı listesini çek
            list_url = f"{instance}/api/v1/captions/{video_id}"
            response = requests.get(list_url, timeout=3) # Hızlı pes et, diğerine geç
            if response.status_code != 200: continue
            
            captions = response.json()
            selected_caption = None
            
            for cap in captions:
                if cap['languageCode'] == 'tr':
                    selected_caption = cap
                    break
            if not selected_caption:
                for cap in captions:
                    if cap['languageCode'] == 'en':
                        selected_caption = cap
                        break
            
            if selected_caption:
                cap_url = f"{instance}{selected_caption['url']}"
                cap_response = requests.get(cap_url, timeout=5)
                
                if cap_response.status_code == 200:
                    lines = cap_response.text.splitlines()
                    text_content = ""
                    for line in lines:
                        if "-->" not in line and line.strip() and not line.strip().isdigit() and "WEBVTT" not in line:
                            text_content += line + " "
                    return clean_xml_transcript(text_content)
        except Exception:
            continue

    # 4. YÖNTEM: Piped API (Genişletilmiş Liste)
    piped_instances = [
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.tokhmi.xyz",
        "https://pipedapi.moomoo.me",
        "https://api.piped.privacy.com.de",
        "https://pipedapi.smnz.de",
        "https://pipedapi.adminforge.de",
        "https://pipedapi.drgns.space",
        "https://api.piped.projectsegfau.lt",
        "https://pipedapi.in.projectsegfau.lt",
        "https://pipedapi.us.projectsegfau.lt",
        "https://lo.piped.video",
        "https://pipedapi.ducks.party"
    ]
    random.shuffle(piped_instances)

    for instance in piped_instances:
        try:
            response = requests.get(f"{instance}/streams/{video_id}", timeout=3)
            if response.status_code != 200: continue
            
            data = response.json()
            subtitles = data.get('subtitles', [])
            
            selected_sub = None
            for sub in subtitles:
                if sub['code'] == 'tr':
                    selected_sub = sub
                    break
            if not selected_sub:
                for sub in subtitles:
                    if sub['code'] == 'en':
                        selected_sub = sub
                        break
            
            if selected_sub:
                sub_url = selected_sub['url']
                sub_response = requests.get(sub_url, timeout=5)
                if sub_response.status_code == 200:
                    lines = sub_response.text.splitlines()
                    text_content = ""
                    for line in lines:
                        if "-->" not in line and line.strip() and not line.strip().isdigit() and "WEBVTT" not in line:
                            text_content += line + " "
                    return clean_xml_transcript(text_content)

        except Exception:
            continue

    st.error("Tüm yöntemler (yt-dlp, youtube-transcript, Invidious, Piped) denendi ancak YouTube IP engellemesi aşılamadı. Lütfen daha sonra tekrar deneyin.")
    return None

def summarize_text(text, api_key):
    """Metni Gemini ile özetler."""
    genai.configure(api_key=api_key)
    
    # Denenecek modeller sırasıyla (En hızlı/ucuzdan -> pahalı/eskiye)
    # 'models/' öneki eklemek daha garantidir
    models_to_try = [
        'models/gemini-1.5-flash', 
        'models/gemini-1.5-pro', 
        'models/gemini-2.5-pro-preview-03-25', # Kullanıcının özel modeli
        'models/gemini-pro',
        'models/gemini-1.0-pro'
    ]
    
    last_error = None
    
    for model_name in models_to_try:
        try:
            # Modeli başlat
            model = genai.GenerativeModel(model_name)
            
            prompt = f"""
            Sen uzman bir ekonomi asistanısın. Aşağıdaki YouTube videosu metnini analiz et ve **KESİNLİKLE** aşağıdaki formatı kullanarak özetle.
            
            **ÖNEMLİ KURALLAR:**
            1. Her başlık için **Markdown formatında (###)** başlık kullan.
            2. Eğer konuşmacı o konu hakkında konuşmadıysa, o başlığın altına sadece "Yorum yok." yaz.
            3. Asla kendi yorumunu katma, sadece konuşmacının dediklerini aktar.
            
            **İSTENEN FORMAT:**
            
            ### 🌍 GENEL PİYASA YORUMU
            - (Konuşmacının genel beklentisi buraya)
            
            ### 🟡 ALTIN & GÜMÜŞ
            - (Ons/Gram tahminleri buraya)
            
            ### 🪙 KRİPTO PARALAR
            - (Bitcoin/Altcoin yorumları buraya)
            
            ### 📈 BORSA İSTANBUL (BIST)
            - (Endeks ve hisse yorumları buraya)
            
            ### 🇺🇸 ABD BORSALARI (NASDAQ/S&P)
            - (Yurt dışı piyasa yorumları buraya)
            
            ### 💵 DÖVİZ (DOLAR/EURO)
            - (Kur tahminleri buraya)

            ---
            **Metin:**
            {text[:15000]}
            """
            
            # Deneme yap
            response = model.generate_content(prompt)
            st.success(f"Özetleme başarıyla tamamlandı! (Kullanılan Model: {model_name})")
            return response.text
            
        except Exception as e:
            last_error = e
            # Hata 429 (Kota) veya 404 (Bulunamadı) ise diğer modele geç
            continue
            
    # Döngü bitti ve hiçbiri çalışmadıysa
    error_msg = f"Tüm modeller denendi ancak başarısız oldu.\nSon hata: {last_error}"
    if "429" in str(last_error):
        error_msg = "Tüm modeller için kota aşıldı (429). Lütfen 1-2 dakika bekleyin."
    elif "404" in str(last_error):
        error_msg = "Modeller bulunamadı (404). API anahtarınızın yetkilerini kontrol edin."
        
    st.error(error_msg)
    return None

# Sidebar - Model Kontrolü
with st.sidebar:
    st.markdown("---")
    if st.button("Erişilebilir Modelleri Listele"):
        if not api_key:
            st.error("Önce API Anahtarı girin.")
        else:
            try:
                genai.configure(api_key=api_key)
                models = list(genai.list_models())
                st.success(f"{len(models)} model bulundu:")
                for m in models:
                    if 'generateContent' in m.supported_generation_methods:
                        st.code(m.name)
            except Exception as e:
                st.error(f"Hata: {e}")

def highlight_keywords(text):
    """Metindeki önemli finansal terimleri sarı ile vurgular."""
    keywords = ["altın", "borsa", "nasdaq", "kripto", "bist", "bitcoin", "dolar", "euro", "gümüş"]
    
    # Regex deseni oluştur (büyük/küçük harf duyarsız)
    for word in keywords:
        pattern = re.compile(f"({word})", re.IGNORECASE)
        text = pattern.sub(r'<span style="background-color: #ffd700; color: black; padding: 0px 4px; border-radius: 3px; font-weight: bold;">\1</span>', text)
    return text

def get_latest_video(channel_url, debug=False):
    """Kanalın en son videolarını bulur (son 24 saat içinde yüklenenler)."""
    try:
        ydl_opts = {
            'extract_flat': True, # Sadece başlıkları al, videoyu indirme
            'quiet': True,
            'playlistend': 15, # Son 15 videoyu kontrol et
            'no_cache_dir': True, # Cache kullanma, taze veri çek
            'ignoreerrors': True, # Hataları görmezden gel
        }
        
        found_videos = []
        last_found_video = None # Hata ayıklama için en son bulunan video
        
        # Türkiye saati (UTC+3)
        tr_timezone = timezone(timedelta(hours=3))
        now = datetime.now(tr_timezone)
        
        # Kanalın "videos" ve "streams" (canlı yayın) sekmelerini kontrol et
        # Önce canlı yayınlara bakalım (genelde bunlar isteniyor)
        target_urls = [f"{channel_url}/streams", f"{channel_url}/videos"]
        
        for target_url in target_urls:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(target_url, download=False)
                    if 'entries' in info and info['entries']:
                        for entry in info['entries']:
                            if entry and entry.get('url') and entry.get('title'):
                                upload_date_str = entry.get('upload_date')
                                
                                if debug:
                                    st.write(f"🔍 Kontrol: {entry['title']} - Tarih: {upload_date_str}")
                                
                                if upload_date_str:
                                    upload_date = datetime.strptime(upload_date_str, '%Y%m%d')
                                    
                                    # En son videoyu kaydet (tarih ne olursa olsun)
                                    # İlk entry genelde en yenisidir, o yüzden sadece ilkini alalım
                                    if last_found_video is None:
                                        last_found_video = {
                                            'title': entry['title'],
                                            'date': upload_date.strftime("%d.%m.%Y")
                                        }
                                    
                                    # Sadece BUGÜN yüklenenleri kontrol et (Gün/Ay/Yıl eşitliği)
                                    if upload_date.date() == now.date():
                                        found_videos.append({
                                            'title': entry['title'],
                                            'url': entry['url'],
                                            'type': 'Canlı Yayın' if 'streams' in target_url else 'Video',
                                            'date': upload_date.strftime("%d.%m.%Y")
                                        })
                                
                except Exception as e:
                    if debug: st.warning(f"Hata ({target_url}): {e}")
                    pass # Hata durumunda diğer URL'ye geç
        
        return found_videos, last_found_video

    except Exception as e:
        if debug: st.error(f"Genel Hata: {e}")
        return None, None

# Ana Arayüz - Sekmeli Yapı
tab1, tab2 = st.tabs(["📺 Video Linki ile Özetle", "📡 Otomatik Takip"])

with tab1:
    video_url = st.text_input("YouTube Video Linkini Yapıştırın:", placeholder="https://www.youtube.com/watch?v=...")

    if st.button("Özetle 🚀", type="primary"):
        if not api_key:
            st.warning("Lütfen önce sol menüden API Anahtarınızı girin.")
        elif not video_url:
            st.warning("Lütfen bir video linki girin.")
        else:
            # video_id = extract_video_id(video_url) # Artık gerek yok, yt-dlp URL istiyor
            
            if video_url:
                with st.spinner("Video altyazıları çekiliyor (Yeni Motor)..."):
                    transcript_text = get_transcript(video_url)
                
                if transcript_text:
                    # Metni hemen göster (Özetlemeyi beklemeden)
                    st.info("✅ Altyazı başarıyla çekildi! Aşağıdan metni kopyalayabilir veya indirebilirsiniz.")
                    
                    # Metni genişletilebilir bir alanda göster (Varsayılan olarak açık)
                    with st.expander("📄 Videonun Tam Metni", expanded=True):
                        st.text_area("Metin", transcript_text, height=300)
                    
                    # Metni indirme butonu
                    st.download_button(
                        label="📥 Metni İndir (TXT)",
                        data=transcript_text,
                        file_name="video_metni.txt",
                        mime="text/plain"
                    )

                    st.markdown("---")
                    st.markdown("### 🤖 Yapay Zeka Özeti")
                    
                    # Özetlemeyi dene
                    with st.spinner("Yapay zeka özeti deniyor... (Hata verirse yukarıdaki metni kullanabilirsiniz)"):
                        summary = summarize_text(transcript_text, api_key)
                    
                    if summary:
                        st.success("Özetleme Başarılı!")
                        st.markdown(highlight_keywords(summary), unsafe_allow_html=True)
                    else:
                        st.warning("⚠️ Otomatik özetleme yapılamadı (API Kotası veya Model Hatası).")
                        st.markdown("""
                        **Ama sorun değil!** 
                        
                        Yukarıdaki **"Metni İndir"** butonuna basıp indirdiğiniz dosyayı:
                        1. **NotebookLM**'e
                        2. **ChatGPT**'ye
                        3. Veya **Claude**'a yükleyerek harika özetler alabilirsiniz.
                        """)
            else:
                st.error("Geçersiz YouTube linki.")

with tab2:
    st.header("Takip Edilen Kanallar")
    st.info("Bu kanalların en son yüklediği videoları veya canlı yayınları otomatik kontrol eder.")
    
    # Geliştirici Modu
    debug_mode = st.checkbox("🛠️ Geliştirici Modu (Hata Ayıklama)", help="Videoların neden bulunamadığını görmek için bunu açın.")

    # Varsayılan Kanallar
    default_channels = {
        "Cihat E. Çiçek": "https://www.youtube.com/@cihatecicek",
        "Tunç Şatıroğlu": "https://www.youtube.com/@TuncSatiroglu"
    }
    
    # Kanal Listesi
    selected_channels = st.multiselect(
        "Kontrol edilecek kanalları seçin:",
        options=list(default_channels.keys()),
        default=list(default_channels.keys())
    )
    
    # Session State Başlatma (Hafıza)
    if 'channel_results' not in st.session_state:
        st.session_state.channel_results = {}

    if st.button("Kanalları Kontrol Et 📡"):
        if not api_key:
             st.warning("Lütfen önce sol menüden API Anahtarınızı girin.")
        else:
            st.session_state.channel_results = {} # Önceki sonuçları temizle
            for channel_name in selected_channels:
                channel_url = default_channels[channel_name]
                with st.status(f"**{channel_name}** kontrol ediliyor...") as status:
                    latest_videos, last_video = get_latest_video(channel_url, debug=debug_mode)
                    
                    if latest_videos:
                        count = len(latest_videos)
                        status.update(label=f"✅ {channel_name}: {count} yeni içerik bulundu!", state="complete")
                        st.session_state.channel_results[channel_name] = latest_videos
                    else:
                        msg = f"❌ {channel_name}: Bugün yeni video yok."
                        if last_video:
                            msg += f" (Son Video: '{last_video['title']}' - {last_video['date']})"
                        status.update(label=msg, state="error")
    
    # Sonuçları Göster (Butona basılmasa bile hafızadan göster)
    if st.session_state.channel_results:
        st.markdown("---")
        st.subheader("Sonuçlar")
        
        for channel_name, videos in st.session_state.channel_results.items():
            st.markdown(f"### 📺 {channel_name}")
            for video_data in videos:
                with st.container():
                    st.markdown(f"**{video_data['title']}** <span style='color:gray; font-size:0.8em'>({video_data['date']})</span>", unsafe_allow_html=True)
                    st.caption(f"Tür: {video_data['type']} | [İzle]({video_data['url']})")
                    
                    # Benzersiz key kullanarak butonu oluştur
                    btn_key = f"btn_{video_data['url']}"
                    
                    if st.button(f"Bu Videoyu Özetle 📝", key=btn_key):
                         with st.spinner(f"{channel_name} videosu özetleniyor..."):
                            transcript_text = get_transcript(video_data['url'])
                            if transcript_text:
                                with st.expander("📄 Tam Metin", expanded=True):
                                    st.text_area(f"Metin - {video_data['title']}", transcript_text, height=200)
                                
                                st.download_button(
                                    label="📥 Metni İndir",
                                    data=transcript_text,
                                    file_name=f"{channel_name}_ozet.txt",
                                    mime="text/plain",
                                    key=f"dl_{video_data['url']}"
                                )
                                
                                # Özetleme
                                summary = summarize_text(transcript_text, api_key)
                                if summary:
                                    st.markdown(highlight_keywords(summary), unsafe_allow_html=True)
                st.markdown("---")

