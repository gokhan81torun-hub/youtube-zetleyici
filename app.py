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
st.title("📊 YouTube Ekonomi Özeti Asistanı")
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

def get_transcript(video_url):
    """Videonun altyazılarını yt-dlp ile çeker."""
    try:
        # Video ID yerine tam URL kullanıyoruz artık
        if "youtube.com" not in video_url and "youtu.be" not in video_url:
             # Eğer sadece ID geldiyse URL'ye çevir
             video_url = f"https://www.youtube.com/watch?v={video_url}"

        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'skip_download': True,  # Videoyu indirme, sadece bilgi al
            'subtitleslangs': ['tr', 'en'],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # Altyazıları kontrol et (önce manuel, sonra otomatik)
            subtitles = info.get('subtitles', {})
            auto_captions = info.get('automatic_captions', {})
            
            # Türkçe altyazı ara
            selected_sub = None
            
            # 1. Manuel Türkçe
            if 'tr' in subtitles:
                selected_sub = subtitles['tr']
            # 2. Otomatik Türkçe
            elif 'tr' in auto_captions:
                selected_sub = auto_captions['tr']
            # 3. Manuel İngilizce
            elif 'en' in subtitles:
                selected_sub = subtitles['en']
            # 4. Otomatik İngilizce
            elif 'en' in auto_captions:
                selected_sub = auto_captions['en']
            
            if selected_sub:
                # Altyazı formatlarından 'json3' veya 'vtt' olanı seç
                # Genelde en sonda en iyi format olur, json3 varsa onu alalım
                sub_url = None
                for fmt in selected_sub:
                    if fmt['ext'] == 'json3':
                        sub_url = fmt['url']
                        break
                    if fmt['ext'] == 'vtt': # Yedek olarak vtt
                        sub_url = fmt['url']
                
                if not sub_url:
                    sub_url = selected_sub[-1]['url'] # Hiçbiri yoksa sonuncuyu al

                # Altyazı içeriğini indir
                response = requests.get(sub_url)
                
                # Basitçe metne çevir (JSON3 veya VTT parse etmek yerine ham metni temizleyebiliriz veya basitçe döndürebiliriz)
                # Şimdilik basitlik adına JSON ise içindeki textleri alalım
                if 'json3' in sub_url or 'fmt=json3' in sub_url:
                    data = response.json()
                    text_content = ""
                    if 'events' in data:
                        for event in data['events']:
                            if 'segs' in event:
                                for seg in event['segs']:
                                    if 'utf8' in seg:
                                        text_content += seg['utf8'] + " "
                    return text_content
                else:
                    # VTT veya diğer formatlar için basit temizlik (daha karmaşık olabilir ama şimdilik yeterli)
                    return "Altyazı formatı desteklenmiyor veya metin çıkarılamadı."
            else:
                st.error("Bu videoda Türkçe veya İngilizce altyazı bulunamadı.")
                return None

    except Exception as e:
        st.error(f"Altyazı alınamadı (yt-dlp): {e}")
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

def get_latest_video(channel_url):
    """Kanalın en son videosunu bulur."""
    try:
        ydl_opts = {
            'extract_flat': True, # Sadece başlıkları al, videoyu indirme
            'playlistend': 1,     # Sadece son 1 video
            'quiet': True,
        }
        
        # Kanalın "videos" ve "streams" (canlı yayın) sekmelerini kontrol et
        # Önce canlı yayınlara bakalım (genelde bunlar isteniyor)
        target_url = f"{channel_url}/streams"
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(target_url, download=False)
                if 'entries' in info and info['entries']:
                    video = info['entries'][0]
                    return {
                        'title': video['title'],
                        'url': video['url'],
                        'type': 'Canlı Yayın'
                    }
            except:
                pass # Canlı yayın yoksa normal videolara bak

            # Normal videolar
            target_url = f"{channel_url}/videos"
            info = ydl.extract_info(target_url, download=False)
            if 'entries' in info and info['entries']:
                video = info['entries'][0]
                return {
                    'title': video['title'],
                    'url': video['url'],
                    'type': 'Video'
                }
                
        return None
    except Exception as e:
        # st.error(f"Kanal kontrol hatası: {e}")
        return None

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
                        st.markdown(summary)
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
                    latest_video = get_latest_video(channel_url)
                    if latest_video:
                        status.update(label=f"✅ {channel_name}: Yeni içerik bulundu!", state="complete")
                        st.session_state.channel_results[channel_name] = latest_video
                    else:
                        status.update(label=f"❌ {channel_name}: Yeni video bulunamadı.", state="error")
    
    # Sonuçları Göster (Butona basılmasa bile hafızadan göster)
    if st.session_state.channel_results:
        st.markdown("---")
        st.subheader("Sonuçlar")
        
        for channel_name, video_data in st.session_state.channel_results.items():
            with st.container():
                st.markdown(f"### {video_data['title']}")
                st.caption(f"Kanal: {channel_name} | Tür: {video_data['type']} | [İzle]({video_data['url']})")
                
                # Benzersiz key kullanarak butonu oluştur
                btn_key = f"btn_{video_data['url']}"
                
                if st.button(f"Bu Videoyu Özetle 📝", key=btn_key):
                     with st.spinner(f"{channel_name} videosu özetleniyor..."):
                        transcript_text = get_transcript(video_data['url'])
                        if transcript_text:
                            with st.expander("📄 Tam Metin", expanded=True):
                                st.text_area(f"Metin - {channel_name}", transcript_text, height=200)
                            
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
                                st.markdown(summary)

# Footer
st.markdown("---")
st.caption("Bu uygulama Google Gemini ve YouTube Transcript API kullanır.")
