"""Learning page for technical stock analysis."""

import streamlit as st


SOURCE_LINKS = {
    "CMT Program": "https://cmtassociation.org/cmt-program/",
    "RSI": "https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/relative-strength-index-rsi",
    "MACD": "https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/macd-moving-average-convergence-divergence-oscillator",
    "ATR": "https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-true-range-atr-and-average-true-range-percent-atrp",
    "OBV": "https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/on-balance-volume-obv",
    "Support & Resistance": "https://www.investopedia.com/trading/support-and-resistance-basics/",
    "MACD Limitations": "https://www.investopedia.com/terms/m/macd.asp",
    "Risk": "https://www.investopedia.com/articles/stocks/09/use-stop-loss.asp",
}


LEARNING_MODULES = [
    {
        "title": "Fondasi Analisis Teknikal",
        "level": "Beginner",
        "goal": "Pahami bahwa teknikal membaca perilaku harga, volume, tren, momentum, volatilitas, dan risiko.",
        "principles": [
            "Harga adalah data utama. Indikator hanya turunan dari harga dan volume, jadi sinyal indikator tidak boleh mengalahkan struktur harga.",
            "Timeframe menentukan makna sinyal. RSI oversold di chart harian berbeda konteksnya dengan RSI oversold di chart mingguan.",
            "Satu indikator jarang cukup. Cari konfirmasi dari tren, momentum, volume, volatilitas, dan area harga penting.",
            "Teknikal tidak memprediksi masa depan secara pasti. Gunakan untuk membuat skenario, bukan kepastian.",
        ],
        "checklist": [
            "Tentukan horizon: trading pendek, swing, atau investasi menengah.",
            "Cek tren utama lebih dulu: harga di atas/bawah MA penting.",
            "Cari area keputusan: support, resistance, atau breakout level.",
            "Validasi momentum dan volume.",
            "Tentukan invalidation point sebelum entry.",
        ],
        "sources": ["CMT Program"],
    },
    {
        "title": "Trend & Moving Average",
        "level": "Beginner",
        "goal": "Gunakan moving average untuk membaca arah dominan dan menghindari entry melawan tren tanpa alasan kuat.",
        "principles": [
            "MA cepat lebih sensitif tetapi lebih banyak noise; MA lambat lebih stabil tetapi terlambat.",
            "Harga di atas MA cepat dan MA lambat sering menunjukkan struktur uptrend yang lebih sehat.",
            "MA cepat di bawah MA lambat menunjukkan tren melemah, terutama jika harga juga berada di bawah keduanya.",
            "Moving average adalah indikator lagging, jadi jangan mengejar harga hanya karena crossover baru terjadi.",
        ],
        "checklist": [
            "Cari urutan sehat: harga > MA cepat > MA lambat.",
            "Untuk saham sideways, MA sering memberi sinyal palsu.",
            "Gunakan pullback ke MA atau support sebagai area observasi, bukan otomatis beli.",
            "Jika harga jauh dari MA, risiko mean reversion biasanya meningkat.",
        ],
    },
    {
        "title": "Support, Resistance & Breakout",
        "level": "Beginner",
        "goal": "Baca area supply-demand agar entry, stop, dan target punya struktur yang jelas.",
        "principles": [
            "Support adalah area tempat permintaan historis pernah cukup kuat menahan penurunan.",
            "Resistance adalah area tempat penawaran historis pernah cukup kuat menahan kenaikan.",
            "Level yang sering dites cenderung lebih diperhatikan pasar, tetapi juga bisa makin rapuh jika terus ditekan.",
            "Breakout lebih berkualitas jika disertai volume, range candle yang meyakinkan, dan retest yang bertahan.",
        ],
        "checklist": [
            "Gambar area, bukan garis tunggal yang terlalu presisi.",
            "Prioritaskan swing high/low yang jelas dan area volume besar.",
            "Waspadai false breakout saat volume lemah atau candle kembali masuk range.",
            "Jangan letakkan stop loss tepat di angka support yang terlalu ramai.",
        ],
    },
    {
        "title": "RSI: Momentum & Exhaustion",
        "level": "Intermediate",
        "goal": "Pakai RSI untuk membaca momentum, bukan sekadar membeli karena oversold atau menjual karena overbought.",
        "principles": [
            "RSI umum memakai periode 14 dan bergerak dalam skala 0-100.",
            "Area 70 sering dibaca overbought dan 30 oversold, tetapi tren kuat bisa membuat RSI lama bertahan di area ekstrem.",
            "Dalam uptrend, RSI sering bertahan di rentang lebih tinggi; dalam downtrend, RSI sering tertahan di rentang lebih rendah.",
            "Divergence berguna sebagai peringatan momentum melemah, tetapi butuh konfirmasi dari price action.",
        ],
        "checklist": [
            "Baca RSI bersama tren utama.",
            "RSI 50 dapat dipakai sebagai garis tengah momentum.",
            "Cari bullish divergence dekat support, bukan di tengah range acak.",
            "Hindari short hanya karena RSI > 70 saat harga sedang breakout kuat.",
        ],
        "sources": ["RSI"],
    },
    {
        "title": "MACD: Tren + Momentum",
        "level": "Intermediate",
        "goal": "Gunakan MACD untuk melihat perubahan momentum berbasis EMA, sambil sadar bahwa sinyalnya bisa terlambat.",
        "principles": [
            "MACD standar memakai EMA 12 dikurangi EMA 26, lalu signal line EMA 9 dari MACD.",
            "MACD di atas nol menunjukkan EMA cepat berada di atas EMA lambat; di bawah nol berarti sebaliknya.",
            "Crossover MACD-signal dapat membantu mendeteksi perubahan momentum, tetapi rawan whipsaw di pasar sideways.",
            "Histogram menunjukkan jarak MACD terhadap signal line, berguna untuk melihat momentum menguat atau melemah.",
        ],
        "checklist": [
            "Bullish crossover lebih kuat jika terjadi dekat support atau setelah base yang rapi.",
            "Bearish crossover lebih relevan jika harga gagal menembus resistance.",
            "Jangan bandingkan nilai MACD antar saham yang harganya berbeda jauh.",
            "Kombinasikan MACD dengan struktur tren dan volume.",
        ],
        "sources": ["MACD", "MACD Limitations"],
    },
    {
        "title": "Volume, MFI & OBV",
        "level": "Intermediate",
        "goal": "Validasi apakah pergerakan harga didukung partisipasi pasar atau hanya gerak tipis tanpa conviction.",
        "principles": [
            "Volume membantu membedakan breakout yang didukung partisipasi dan breakout yang rapuh.",
            "OBV menjumlahkan volume saat harga naik dan mengurangi volume saat harga turun untuk membaca tekanan beli/jual kumulatif.",
            "MFI mirip oscillator berbasis harga dan volume; area ekstrem bisa memberi peringatan inflow/outflow berlebih.",
            "Volume spike satu hari bisa mendistorsi pembacaan, jadi lihat tren volume, bukan hanya satu bar.",
        ],
        "checklist": [
            "Breakout sehat idealnya disertai volume di atas rata-rata.",
            "Harga naik tetapi OBV turun dapat menjadi peringatan distribusi.",
            "Harga turun tetapi OBV membaik dapat menandakan akumulasi awal, tetap tunggu konfirmasi harga.",
            "Untuk saham tidak likuid, sinyal volume lebih mudah menipu.",
        ],
        "sources": ["OBV"],
    },
    {
        "title": "ATR, Volatilitas & Position Sizing",
        "level": "Intermediate",
        "goal": "Pakailah volatilitas untuk menempatkan stop loss dan ukuran posisi dengan lebih rasional.",
        "principles": [
            "ATR mengukur volatilitas, bukan arah harga.",
            "ATR menangkap range harian dan gap, sehingga berguna untuk menilai jarak stop yang wajar.",
            "ATRP menormalkan ATR terhadap harga, sehingga lebih baik untuk membandingkan volatilitas antar saham.",
            "Stop loss yang terlalu sempit pada saham volatil sering tersentuh oleh noise normal.",
        ],
        "checklist": [
            "Tentukan risiko per transaksi terlebih dahulu, misalnya 0.5%-1% dari modal.",
            "Gunakan support dan ATR untuk mencari stop yang punya alasan teknikal.",
            "Jika jarak stop terlalu lebar, kecilkan posisi, bukan memaksakan stop terlalu dekat.",
            "Saham dengan ATRP tinggi butuh ukuran posisi lebih kecil.",
        ],
        "sources": ["ATR", "Risk"],
    },
    {
        "title": "Workflow Analisis yang Disiplin",
        "level": "Advanced",
        "goal": "Gabungkan indikator menjadi keputusan yang terstruktur, bukan kumpulan sinyal yang saling bertabrakan.",
        "principles": [
            "Mulai dari market regime: trend, sideways, volatile, atau quiet.",
            "Cari confluence: tren searah, momentum membaik, volume mendukung, dan harga dekat area risk/reward menarik.",
            "Setiap setup harus punya invalidation point, target realistis, dan ukuran posisi.",
            "Catat hasil transaksi untuk mengevaluasi apakah edge benar-benar ada.",
        ],
        "checklist": [
            "Trend: harga dan MA mendukung?",
            "Area: dekat support, breakout, atau malah dekat resistance?",
            "Momentum: RSI/MACD mengonfirmasi atau melemah?",
            "Volume: OBV/MFI mendukung atau divergen?",
            "Risk: stop, target, dan risk/reward masuk akal?",
        ],
    },
]


GLOSSARY = [
    ("Trend", "Arah dominan harga dalam periode tertentu: naik, turun, atau sideways."),
    ("Support", "Area harga yang historis sering menahan penurunan karena permintaan muncul."),
    ("Resistance", "Area harga yang historis sering menahan kenaikan karena penawaran muncul."),
    ("Breakout", "Harga keluar dari area resistance/support penting; kualitasnya perlu konfirmasi volume dan follow-through."),
    ("RSI", "Oscillator momentum 0-100 untuk membaca kekuatan gerak harga dan potensi kondisi ekstrem."),
    ("MACD", "Indikator momentum berbasis selisih EMA cepat dan EMA lambat."),
    ("ATR", "Ukuran volatilitas rata-rata yang memasukkan range dan gap; bukan indikator arah."),
    ("OBV", "Indikator volume kumulatif untuk membaca tekanan akumulasi atau distribusi."),
    ("Risk/Reward", "Perbandingan potensi keuntungan terhadap potensi kerugian jika stop loss tersentuh."),
]


def _render_header() -> None:
    st.markdown(
        """
        <div style="padding:28px 0 18px 0;border-bottom:1px solid #38383A;margin-bottom:24px;">
            <div style="font-size:0.72rem;font-weight:600;color:#8E8E93;
                        text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">
                Learning Center
            </div>
            <h1 style="font-size:1.9rem;font-weight:700;color:#F5F5F7;margin:0;line-height:1.2;">
                Belajar Analisis Teknikal Saham
            </h1>
            <p style="font-size:0.95rem;color:#8E8E93;max-width:760px;margin:10px 0 0 0;line-height:1.65;">
                Materi ringkas dan praktis untuk membaca chart IDX dengan disiplin.
                Ini edukasi, bukan rekomendasi beli atau jual.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_module_card(module: dict) -> None:
    st.markdown(
        f"<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:4px;'>{module['title']}</h3>",
        unsafe_allow_html=True,
    )
    st.caption(f"{module['level']} · {module['goal']}")

    left, right = st.columns([1.2, 1], gap="large")
    with left:
        st.markdown("**Prinsip utama**")
        for item in module["principles"]:
            st.markdown(f"- {item}")

    with right:
        st.markdown("**Checklist praktik**")
        for item in module["checklist"]:
            st.checkbox(item, key=f"{module['title']}_{item}")

    sources = module.get("sources", [])
    if sources:
        source_text = " · ".join(
            f"[{name}]({SOURCE_LINKS[name]})" for name in sources
        )
        st.caption(f"Referensi: {source_text}")


def _render_playbook() -> None:
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;'>Playbook Cepat</h3>",
                unsafe_allow_html=True)
    st.caption("Urutan baca chart yang bisa dipakai sebelum membuka posisi.")

    rows = [
        {
            "Step": "1. Regime",
            "Question": "Saham sedang trend, sideways, atau volatile?",
            "Avoid": "Memakai strategi breakout saat pasar jelas sideways.",
        },
        {
            "Step": "2. Structure",
            "Question": "Harga dekat support, resistance, MA, atau breakout level?",
            "Avoid": "Entry di tengah range tanpa area invalidation.",
        },
        {
            "Step": "3. Momentum",
            "Question": "RSI dan MACD mendukung arah harga?",
            "Avoid": "Membeli hanya karena RSI oversold di downtrend kuat.",
        },
        {
            "Step": "4. Volume",
            "Question": "Volume, OBV, atau MFI mengonfirmasi pergerakan?",
            "Avoid": "Mengejar breakout volume tipis.",
        },
        {
            "Step": "5. Risk",
            "Question": "Stop loss, target, dan ukuran posisi sudah jelas?",
            "Avoid": "Mengubah stop loss lebih jauh saat posisi rugi.",
        },
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_glossary() -> None:
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;'>Glosarium</h3>",
                unsafe_allow_html=True)
    for term, meaning in GLOSSARY:
        with st.expander(term):
            st.markdown(meaning)


def _render_sources() -> None:
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;'>Sumber Belajar Lanjutan</h3>",
                unsafe_allow_html=True)
    st.caption("Dipilih untuk melengkapi indikator yang dipakai PastiCuan.")
    for name, url in SOURCE_LINKS.items():
        st.markdown(f"- [{name}]({url})")


def render_learning_page() -> None:
    _render_header()

    st.info(
        "Gunakan materi ini sebagai kerangka edukasi. Keputusan investasi tetap perlu "
        "mempertimbangkan profil risiko, likuiditas saham, kondisi pasar, dan rencana exit."
    )

    tab1, tab2, tab3, tab4 = st.tabs([
        "Materi",
        "Playbook",
        "Glosarium",
        "Sumber",
    ])

    with tab1:
        for idx, module in enumerate(LEARNING_MODULES):
            if idx:
                st.divider()
            _render_module_card(module)

    with tab2:
        _render_playbook()

    with tab3:
        _render_glossary()

    with tab4:
        _render_sources()
