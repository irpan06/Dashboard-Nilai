
__author__ = "irr"
__version__ = "1.0.0"

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
import altair as alt
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# ==============================================================================
# KONFIGURASI DAN FUNGSI BANTUAN
# ==============================================================================

# Mapping nilai huruf ke bobot angka
NILAI_MAP = {
    "A": 4.0,
    "AB": 3.5,
    "B": 3.0,
    "BC": 2.5,
    "C": 2.0,
    "D": 1.0,
    "E": 0.0,
}


def display_main_app():
    def hitung_jatah_sks(ips):
        if ips < 2:
            return 15
        elif 2 <= ips <= 2.5:
            return 18
        elif 2.51 <= ips <= 3:
            return 20
        else:  # ips > 3
            return 24

    def semester_sort_key(semester_str):
        """Kunci pengurutan kustom untuk string semester (contoh: '2023/2024 Ganjil')."""
        if not isinstance(semester_str, str) or "/" not in semester_str:
            return (9999, 9999)
        try:
            year_part = semester_str.split("/")[0].strip()
            year = int(year_part)
            order = 0 if "Ganjil" in semester_str else 1
            return (year, order)
        except (ValueError, IndexError):
            return (9999, 9999)

    def smart_find_taken_courses(kurikulum_df, transkrip_list):
        """
        Mencari mata kuliah yang sudah diambil dengan metode 2 tahap:
        1. Cari kecocokan 100% (exact match).
        2. Cari kemiripan nama (similarity match) untuk sisanya.
        """
        THRESHOLD = 0.77  # Threshold untuk tahap kedua

        # Buat salinan agar daftar asli tidak berubah
        available_transcript_courses = [name.lower() for name in transkrip_list]
        kurikulum_courses = kurikulum_df.copy()
        kurikulum_courses["lower_name"] = kurikulum_courses["Mata Kuliah"].str.lower()

        taken_indices = []

        # --- Tahap 1: Exact Matching ---
        for index, row in kurikulum_courses.iterrows():
            if row["lower_name"] in available_transcript_courses:
                taken_indices.append(index)
                available_transcript_courses.remove(row["lower_name"])

        # --- Tahap 2: Similarity Matching untuk sisanya ---
        remaining_kurikulum = kurikulum_courses.drop(taken_indices)

        for index, row in remaining_kurikulum.iterrows():
            if not available_transcript_courses:
                break  # Hentikan jika semua MK transkrip sudah terpetakan

            best_match, best_score = None, 0
            for trans_course in available_transcript_courses:
                score = SequenceMatcher(None, row["lower_name"], trans_course).ratio()
                if score > best_score:
                    best_score = score
                    best_match = trans_course

            if best_score >= THRESHOLD:
                taken_indices.append(index)
                available_transcript_courses.remove(best_match)

        # Kembalikan DataFrame dari kurikulum yang sudah teridentifikasi
        return kurikulum_df.loc[taken_indices]

    def create_donut_chart(value, title):
        """Membuat grafik donat untuk menampilkan IPK."""
        if value < 2:
            primary_color = "#FF4136"  # Merah
        elif 2 <= value < 3:
            primary_color = "#FFDC00"  # Kuning
        else:
            primary_color = "#2ECC40"  # Hijau

        fig = go.Figure(
            go.Pie(
                values=[value, 4.0 - value],
                labels=[title, "Sisa"],
                hole=0.7,
                marker_colors=[primary_color, "rgba(0,0,0,0.1)"],
                textinfo="none",
                hoverinfo="none",
                sort=False,
                direction="clockwise",
            )
        )
        fig.update_layout(
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
            showlegend=False,
            annotations=[
                dict(
                    text=f"<b>{title}</b>",
                    x=0.5,
                    y=0.60,
                    font_size=20,
                    showarrow=False,
                    font=dict(color="grey"),
                ),
                dict(
                    text=f"<b>{value:.2f}</b>",
                    x=0.5,
                    y=0.45,
                    font_size=40,
                    showarrow=False,
                    font=dict(color=primary_color),
                ),
            ],
        )
        return fig

    def styled_progress_bar(value, total, color, label):
        """
        Membuat progress bar kustom dengan teks dan warna yang bisa diubah.
        """
        percentage = min(value / total, 1.0)

        # Logika untuk menampilkan status "Target Terpenuhi"
        if percentage >= 1.0:
            if value >= 144:
                status_text = "<span style='color:green; font-weight:bold;'>S.Si.</span>"
                bar_color = "green"
            else:
                status_text = f"<span style='color:green; font-weight:bold;'>{value} / {total}</span>"
                bar_color = "green"
        else:
            status_text = f"{value} / {total}"
            bar_color = color

        bar_html = f"""
            <div style="margin-top: 10px;">
                <div style="margin-bottom: 5px;">{label}</div>
                <div style="background-color: #f1f1f1; border-radius: 10px; padding: 2px;">
                    <div style="background-color: {bar_color}; width: {percentage*100}%; border-radius: 8px; height: 20px;">
                    </div>
                </div>
                <div style="text-align: right; font-size: 0.9em; color: grey;">{status_text}</div>
            </div>
        """
        st.markdown(bar_html, unsafe_allow_html=True)

    # ==============================================================================
    # PEMUATAN DATA
    # ==============================================================================
    try:
        transkrip_df = st.session_state.df.copy()
        transkrip_df["Semester"] = transkrip_df["Semester"].str.split(" - ").str[0]
        transkrip_ori = transkrip_df.copy()
        transkrip_ori["Semester"] = transkrip_ori["Semester"].str.split(" - ").str[0]

        # import file mk wajib dan kbk
        kurikulum_df = pd.read_excel("data/mk wajib.xlsx")
        kbk_df = pd.read_excel("data/mk kbk.xlsx")
    except FileNotFoundError:
        st.error("Pastikan semua file (transkrip, mk wajib, mk kbk) telah diunggah.")
        st.stop()

    # 1. Proses Transkrip & Atasi Duplikasi
    transkrip_df["Bobot_numeric"] = pd.to_numeric(transkrip_df["Bobot"], errors="coerce")  # buang BT
    df_graded = transkrip_df[
        (transkrip_df["Bobot_numeric"].notna()) & (transkrip_df["Nilai"] != "E")
    ].copy()
    df_graded_sorted = df_graded.sort_values(
        by=["Nama Mata Ajar", "Bobot_numeric"], ascending=[True, False]
    )
    df_unique_graded = df_graded_sorted.drop_duplicates(
        subset="Nama Mata Ajar", keep="first"
    )  # ambil hanya mk dengan niai tertinggi (tanpa ada mk BT)

    df_ongoing = transkrip_df[transkrip_df["Bobot_numeric"].isna()].copy()
    df_ongoing = df_ongoing[
        ~df_ongoing["Nama Mata Ajar"].isin(df_unique_graded["Nama Mata Ajar"])
    ]  # filter untuk hanya mata kuliah yang baru diambil (belum ada nilai)

    # 2. Hitung IPK & total SKS lulus
    total_sks_graded = df_unique_graded["SKS"].sum()  # hitung total sks mk tanpa BT dan tanpa mk dobel
    total_bobot_graded = df_unique_graded["Bobot_numeric"].sum()  # hitung total bobot mk tanpa BT
    ipk_awal = (
        total_bobot_graded / total_sks_graded if total_sks_graded > 0 else 0.0
    )  # ipk -> tanpa BT dan hanya nilai tertinggi

    total_sks_ongoing = df_ongoing["SKS"].sum()  # hitung sks mk BT

    # 3. Hitung IPS per semester
    ips_df = (
        df_graded.groupby("Semester")
        .agg(Total_Bobot=("Bobot_numeric", "sum"), Total_SKS=("SKS", "sum"))
        .reset_index()
    )

    ips_df["IPS"] = ips_df["Total_Bobot"] / ips_df["Total_SKS"]
    ips_df = ips_df.sort_values(by="Semester", key=lambda s: s.map(semester_sort_key)).reset_index(drop=True)
    ips_df["Semester"] = ips_df["Semester"].str.split(" - ").str[0]
    ips_df["SemesterLabel"] = [f"Semester {i+1}" for i in ips_df.index]
    ips_df["IPS_Lalu"] = ips_df["IPS"].shift(1)
    ips_df["Jatah_SKS"] = ips_df["IPS_Lalu"].apply(lambda x: None if pd.isna(x) else hitung_jatah_sks(x))
    ips_df["Jatah_SKS"] = ips_df["Jatah_SKS"].fillna(0).astype(int)

    # 3. Logika Pencocokan Berdasarkan NAMA
    kurikulum_mk_list = kurikulum_df["Mata Kuliah"].dropna().tolist()
    kbk_mk_list = kbk_df["Mata Kuliah"].dropna().tolist()
    unique_mk_list = df_unique_graded["Nama Mata Ajar"].dropna().tolist()
    transkrip_mk_list = transkrip_df["Nama Mata Ajar"].tolist()

    # 3. Identifikasi MK yang Sudah dan Belum Diambil (Menggunakan Fungsi Baru)
    # HANYA MATKUL YANG TELAH DIAMBIL, BUKAN MATKUL BT
    df_wajib_terambil = smart_find_taken_courses(kurikulum_df, unique_mk_list)
    df_kbk_terambil = smart_find_taken_courses(kbk_df, unique_mk_list)

    # Cari MK yang belum diambil dengan membandingkan DataFrame
    df_wajib_belum_terambil = kurikulum_df[
        ~kurikulum_df["Mata Kuliah"].isin(df_wajib_terambil["Mata Kuliah"])
    ]
    df_kbk_belum_terambil = kbk_df[
        ~kbk_df["Mata Kuliah"].isin(df_kbk_terambil["Mata Kuliah"])
    ]

    sks_wajib_terambil = df_wajib_terambil["SKS"].sum()
    sks_kbk_terambil = df_kbk_terambil["SKS"].sum()

    # UNTUK SEMUA MATKUL YANG ADA DI TRANSKRIP -> TERMASUK MATKUL BT
    df_wajib_transkrip = smart_find_taken_courses(kurikulum_df, transkrip_ori["Nama Mata Ajar"].to_list())
    df_kbk_transkrip = smart_find_taken_courses(kbk_df, transkrip_ori["Nama Mata Ajar"].to_list())

    # Cari MK yang belum diambil dengan membandingkan DataFrame -> untuk tabel cek
    df_wajib_BT = kurikulum_df[~kurikulum_df["Mata Kuliah"].isin(df_wajib_transkrip["Mata Kuliah"])]
    df_kbk_BT = kbk_df[~kbk_df["Mata Kuliah"].isin(df_kbk_transkrip["Mata Kuliah"])]

    sks_wajib_transkrip = df_wajib_transkrip["SKS"].sum()
    sks_kbk_transkrip = df_kbk_transkrip["SKS"].sum()

    # Tetapkan total SKS Wajib & target KBK
    total_sks_wajib = kurikulum_df["SKS"].sum()
    SKS_TARGET_KBK = 14

    # Pembagian semester
    list_semester = sorted(transkrip_ori["Semester"].dropna().unique(), key=semester_sort_key)
    list_semester.insert(0, "Overview")

    # ==============================================================================
    # TATA LETAK APLIKASI STREAMLIT
    # ==============================================================================
    st.set_page_config(layout="centered")
    st.sidebar.title("🏛️ Our Campus")

    if "user_info" in st.session_state and st.session_state.user_info:
        user_info = st.session_state.user_info
        nama = user_info.get("Nama Lengkap", "Tidak Ditemukan")
        st.sidebar.subheader("")
        st.sidebar.subheader(f"👤 {nama}")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.df = None
        st.rerun()

    st.sidebar.write("")
    pilihan_semester = st.sidebar.selectbox("Pilih Semester:", options=list_semester)

    if st.sidebar.toggle("Simulasi Perolehan Nilai"):
        if st.sidebar.button("Reset"):
            st.session_state.grid_key_counter += 1
            st.rerun()
        st.title("Simulasi Perolehan Nilai", help="Ubah nilai pada Indeks Nilai")
        st.markdown("---")

        col1, col2 = st.columns(2)

        # 4. Tentukan dataframe mana yang akan ditampilkan di tabel berdasarkan checkbox
        df_display = pd.concat([df_unique_graded, df_ongoing], ignore_index=True).drop(columns=["Bobot_numeric"])

        st.markdown("---")
        # --- Konfigurasi AgGrid (tidak ada perubahan) ---
        gb = GridOptionsBuilder.from_dataframe(df_display)
        gb.configure_default_column(headerClass="ag-left-aligned-header")
        gb.configure_column("Nama Mata Ajar", editable=False, width=300, cellStyle={"text-align": "left"})
        gb.configure_column("SKS", editable=False, width=80, cellStyle={"text-align": "center"})
        gb.configure_column(
            "Nilai",
            header_name="Indeks Nilai",
            editable=True,
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": list(NILAI_MAP.keys())},
            width=100,
            cellStyle={"text-align": "center"},
        )
        gb.configure_column(
            "Bobot",
            editable=False,
            width=100,
            cellStyle={"text-align": "center"},
            valueGetter=JsCode(
                """
                function(params) {
                    if (params.data.Nilai === '*BT' || !params.data.Nilai) return 0;
                    const map = {"A":4.0,"AB":3.5,"B":3.0,"BC":2.5,"C":2.0,"D":1.0,"E":0.0};
                    const idx = map[params.data.Nilai] || 0;
                    const sks = Number(params.data.SKS) || 0;
                    return sks * idx;
                }
                """
            ),
            valueFormatter=JsCode("function(params){ return Number(params.value || 0).toFixed(2); }"),
        )
        gb.configure_column("Kode MA", editable=False, hide=True)
        gb.configure_column("Semester", editable=False, hide=True)
        if "Indeks" in df_display.columns:
            gb.configure_column("Indeks", hide=True)
        grid_options = gb.build()

        # Gunakan kunci dinamis untuk AgGrid agar bisa di-reset
        grid_response = AgGrid(
            df_display,
            gridOptions=grid_options,
            update_mode="VALUE_CHANGED",
            fit_columns_on_grid_load=True,
            allow_unsafe_jscode=True,
            key=f"transcript_grid_{st.session_state.grid_key_counter}",
            theme="balham",
        )
        edited_df = pd.DataFrame(grid_response["data"])

        # --- Perhitungan ulang IPK di backend ---
        edited_df["Indeks"] = edited_df["Nilai"].map(NILAI_MAP)
        edited_df["SKS"] = pd.to_numeric(edited_df["SKS"], errors="coerce")
        edited_df["Bobot"] = edited_df["Indeks"] * edited_df["SKS"]
        edited_filter = edited_df.dropna(subset=["Bobot"])
        edited_sorted = edited_filter.sort_values(by=["Kode MA", "Bobot"], ascending=[True, False])
        edited_unique = edited_sorted.drop_duplicates(subset="Kode MA", keep="first")
        total_sks_edited = edited_unique["SKS"].sum()
        total_bobot_edited = edited_unique["Bobot"].sum()
        ipk_akhir = total_bobot_edited / total_sks_edited if total_sks_edited > 0 else 0.0

        with col1:
            st.plotly_chart(create_donut_chart(ipk_akhir, "IPK"), use_container_width=True)

        with col2:
            st.write("")
            nilai_counts = edited_df["Nilai"].value_counts().reindex(list(NILAI_MAP.keys()), fill_value=0)

            fig, ax = plt.subplots()
            bars = ax.bar(nilai_counts.index, nilai_counts.values, color="#0074D9")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.set_ylim(0, nilai_counts.max() + 1.5)
            for bar in bars:
                height = bar.get_height()
                ax.annotate(
                    f"{int(height)}",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                )
            st.pyplot(fig)

    else:
        if pilihan_semester == "Overview":
            # Overview
            st.title("Transkrip Akademik")
            st.markdown("---")

            col1, col2 = st.columns(2)

            with col1:
                st.plotly_chart(create_donut_chart(ipk_awal, "IPK"), use_container_width=True)

            with col2:
                include_ongoing = st.checkbox(
                    "Sertakan mata kuliah yang sedang diambil",
                    value=False,
                    help="Tidak termasuk dalam perhitungan IPK",
                )
                if include_ongoing:
                    # --- Progress Total SKS (Warna Biru) ---
                    styled_progress_bar(
                        value=total_sks_graded + total_sks_ongoing,
                        total=144,
                        color="#007bff",
                        label="SKS Terambil",
                    )

                    # --- Progress MK Wajib (Warna Oranye) ---
                    styled_progress_bar(
                        value=sks_wajib_transkrip,
                        total=total_sks_wajib,
                        color="#ff0000",
                        label="MK Wajib",
                    )

                    # --- Progress MK Pilihan (KBK) (Warna Ungu) ---
                    styled_progress_bar(
                        value=sks_kbk_transkrip,
                        total=SKS_TARGET_KBK,
                        color="#e4de1c",
                        label="MK Pilihan (KBK)",
                    )
                else:
                    # --- Progress Total SKS (Warna Biru) ---
                    styled_progress_bar(
                        value=total_sks_graded, total=144, color="#007bff", label="SKS Terambil"
                    )

                    # --- Progress MK Wajib (Warna Oranye) ---
                    styled_progress_bar(
                        value=sks_wajib_terambil,
                        total=total_sks_wajib,
                        color="#ff0000",
                        label="MK Wajib",
                    )

                    # --- Progress MK Pilihan (KBK) (Warna Ungu) ---
                    styled_progress_bar(
                        value=sks_kbk_terambil,
                        total=SKS_TARGET_KBK,
                        color="#e4de1c",
                        label="MK Pilihan (KBK)",
                    )

            st.markdown("---")
            st.write("")
            st.write("")
            col_grafik1, col_grafik2 = st.columns(2)

            with col_grafik1:
                st.subheader("Distribusi Nilai")
                nilai_counts = df_unique_graded["Nilai"].value_counts().reindex(list(NILAI_MAP.keys()), fill_value=0)

                fig, ax = plt.subplots()
                bars = ax.bar(nilai_counts.index, nilai_counts.values, color="#0074D9")
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.set_ylim(0, nilai_counts.max() + 1.5)
                for bar in bars:
                    height = bar.get_height()
                    ax.annotate(
                        f"{int(height)}",
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                    )
                st.pyplot(fig)

            with col_grafik2:
                st.subheader("Grafik IPS")
                x = ips_df.index + 1
                y = ips_df["IPS"]

                fig, ax = plt.subplots()
                ax.plot(x, y, marker="o", markersize=8, color="#2ECC40", linewidth=2)
                for i, val in enumerate(y):
                    ax.text(x[i], val + 0.05, f"{val:.2f}", ha="center", va="bottom", fontsize=10, color="#333")
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.set_ylim(1, 4.1)
                ax.set_xlim(0.5, len(x) + 0.5)
                ax.set_xticks(x)
                ax.set_xticklabels(ips_df["SemesterLabel"], rotation=45, ha="right")
                st.pyplot(fig)

            st.markdown("---")

            # --- BAGIAN TRANSKRIP DAN GRAFIK ---
            st.header("Transkrip Nilai", help="Tabel ini hanya menampilkan nilai terbaik jika ada mata kuliah yang diulang.")

            if include_ongoing:
                df_display = pd.concat([df_unique_graded, df_ongoing], ignore_index=True).drop(columns=["Bobot_numeric"])
            else:
                df_display = df_unique_graded.drop(columns=["Bobot_numeric"])

            # Konfigurasi AgGrid untuk Transkrip
            gb_transkrip = GridOptionsBuilder.from_dataframe(df_display[["Semester", "Nama Mata Ajar", "SKS", "Nilai", "Bobot"]])
            gb_transkrip.configure_default_column(editable=False, headerClass="ag-left-aligned-header")
            gb_transkrip.configure_column("Nama Mata Ajar", width=400)
            gb_transkrip.configure_column("SKS", width=100, cellStyle={"text-align": "center"})
            gb_transkrip.configure_column("Nilai", width=100, cellStyle={"text-align": "center"})
            gb_transkrip.configure_column("Bobot", width=100, cellStyle={"text-align": "center"})
            grid_options_transkrip = gb_transkrip.build()

            AgGrid(
                df_display,
                gridOptions=grid_options_transkrip,
                fit_columns_on_grid_load=True,
                theme="balham",
                allow_unsafe_jscode=True,
            )

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("---")

            # --- BAGIAN MATA KULIAH BELUM DIAMBIL ---
            st.header("Mata Kuliah Belum Diambil")

            # Tabel untuk Mata Kuliah Wajib
            st.subheader("MK Wajib")
            gb_wajib = GridOptionsBuilder.from_dataframe(df_wajib_BT[["Semester", "Mata Kuliah", "SKS", "Prasyarat"]])
            gb_wajib.configure_column("Mata Kuliah", width=400)
            gb_wajib.configure_column("SKS", width=100, cellStyle={"text-align": "center"})
            grid_options_wajib = gb_wajib.build()
            AgGrid(df_wajib_BT, gridOptions=grid_options_wajib, fit_columns_on_grid_load=True, theme="balham")

            # Tabel untuk Mata Kuliah Pilihan (KBK)
            st.subheader("MK Pilihan (KBK)")
            gb_kbk = GridOptionsBuilder.from_dataframe(df_kbk_BT[["Semester", "Mata Kuliah", "SKS", "Prasyarat"]])
            gb_kbk.configure_column("Mata Kuliah", width=400)
            gb_kbk.configure_column("SKS", width=100, cellStyle={"text-align": "center"})
            grid_options_kbk = gb_kbk.build()
            AgGrid(df_kbk_BT, gridOptions=grid_options_kbk, fit_columns_on_grid_load=True, theme="balham")

        else:
            for sem in list_semester:
                if pilihan_semester == sem:
                    df_sem = transkrip_ori[transkrip_ori["Semester"] == pilihan_semester][["Nama Mata Ajar", "SKS", "Nilai", "Bobot"]]
                    if (df_sem["Nilai"] == "*BT").any():  # untuk semester sekarang
                        df_sem["Bobot"] = pd.to_numeric(df_sem["Bobot"], errors="coerce")
                        df_sem["Bobot"] = df_sem["Bobot"].fillna(0).astype(int)
                        st.title(f"Semester {sem}")
                        st.markdown("---")

                        col1, col2 = st.columns(2)

                        with col1:
                            st.plotly_chart(create_donut_chart(0, "IPS"), use_container_width=True)
                        with col2:
                            styled_progress_bar(
                                value=ips_df["Jatah_SKS"].iloc[-1], total=24, color="#007bff", label="Jatah SKS"
                            )

                            styled_progress_bar(value=df_sem["SKS"].sum(), total=24, color="#ff0000", label="Jumlah SKS")

                            # --- Progress MK Pilihan (KBK) (Warna Ungu) ---
                            styled_progress_bar(value=df_sem["Bobot"].sum(), total=96, color="#e4de1c", label="Total Bobot")

                        st.warning("Nilai anda belum keluar")
                        st.markdown("---")

                        gb_wajib = GridOptionsBuilder.from_dataframe(df_sem[["Nama Mata Ajar", "SKS", "Nilai", "Bobot"]])
                        gb_wajib.configure_column("Nama Mata Ajar", width=400)
                        gb_wajib.configure_column("SKS", width=100, cellStyle={"text-align": "center"})
                        gb_wajib.configure_column("Nilai", width=100, cellStyle={"text-align": "center"})
                        gb_wajib.configure_column("Bobot", width=100, cellStyle={"text-align": "center"})
                        grid_options_wajib = gb_wajib.build()
                        AgGrid(df_sem, gridOptions=grid_options_wajib, fit_columns_on_grid_load=True, theme="balham")

                    else:  # tampilan untuk semester sebelumnya
                        st.title(f"Semester {sem}")
                        st.markdown("---")

                        col1, col2 = st.columns(2)

                        with col1:
                            ips_value = ips_df.loc[ips_df["Semester"] == pilihan_semester, "IPS"].values[0]
                            ips = Decimal(ips_value)
                            st.plotly_chart(create_donut_chart(ips_value, "IPS"), use_container_width=True)

                        with col2:
                            styled_progress_bar(
                                value=ips_df.loc[ips_df["Semester"] == pilihan_semester, "Jatah_SKS"].values[0],
                                total=24,
                                color="#007bff",
                                label="Jatah SKS",
                            )

                            styled_progress_bar(value=df_sem["SKS"].sum(), total=24, color="#ff0000", label="Jumlah SKS")

                            # --- Progress MK Pilihan (KBK) (Warna Ungu) ---
                            styled_progress_bar(
                                value=ips_df.loc[ips_df["Semester"] == pilihan_semester, "Total_Bobot"].values[0],
                                total=96,
                                color="#e4de1c",
                                label="Total Bobot",
                            )

                        st.info(
                            f"IPS anda {ips.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}, "
                            f"Jatah SKS anda semester depan adalah {hitung_jatah_sks(ips_value)} SKS"
                        )
                        st.markdown("---")

                        gb_wajib = GridOptionsBuilder.from_dataframe(df_sem[["Nama Mata Ajar", "SKS", "Nilai", "Bobot"]])
                        gb_wajib.configure_column("Nama Mata Ajar", width=400)
                        gb_wajib.configure_column("SKS", width=100, cellStyle={"text-align": "center"})
                        gb_wajib.configure_column("Nilai", width=100, cellStyle={"text-align": "center"})
                        gb_wajib.configure_column("Bobot", width=100, cellStyle={"text-align": "center"})
                        grid_options_wajib = gb_wajib.build()
                        AgGrid(df_sem, gridOptions=grid_options_wajib, fit_columns_on_grid_load=True, theme="balham")


# --- Fungsi untuk menampilkan form login ---
def display_login_form():
    # 1. Pastikan Session tetap hidup dan tidak berubah
    if 'session' not in st.session_state:
        st.session_state.session = requests.Session()
        st.session_state.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://mahasiswa.unair.ac.id/"
        })
    
    session = st.session_state.session
    base_url = "https://mahasiswa.unair.ac.id/"

    # 2. Fungsi untuk mengambil Token & Captcha (Hanya dipanggil jika belum ada)
    def fetch_security_data():
        try:
            resp = session.get(base_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Ambil CSRF Token (Sesuai HTML: name="csrf_token")
            token_el = soup.find("input", {"name": "csrf_token"})
            token = token_el.get("value", "") if token_el else ""
            
            # Ambil URL Gambar Captcha (Sesuai HTML: alt="captcha")
            img_tag = soup.find("img", {"alt": "captcha"})
            captcha_bytes = None
            if img_tag:
                c_src = img_tag.get("src")
                c_url = base_url + c_src if not c_src.startswith("http") else c_src
                # Header Accept agar server tahu kita minta gambar
                c_resp = session.get(c_url, headers={"Accept": "image/*"}, timeout=10)
                if "image" in c_resp.headers.get("Content-Type", ""):
                    captcha_bytes = c_resp.content
            
            return token, captcha_bytes
        except Exception as e:
            st.error(f"Gagal menghubungi server Unair: {e}")
            return "", None

    # Inisialisasi data keamanan jika belum ada
    if 'login_token' not in st.session_state or st.session_state.login_token == "":
        t, c = fetch_security_data()
        st.session_state.login_token = t
        st.session_state.captcha_bytes = c

    # --- TAMPILAN FORM ---
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form(key="autentifikasi"):
            st.title("Login Cyber", help="NIM dan Password Anda tidak disimpan.")
            input_nim = st.text_input(label="NIM")
            input_pw = st.text_input(label="Password", type="password")
            
            # Tampilkan Gambar Captcha
            if st.session_state.captcha_bytes:
                st.image(st.session_state.captcha_bytes, caption="Masukkan kode di atas")
            else:
                st.warning("Gagal memuat Captcha. Silakan muat ulang halaman.")
            
            input_captcha = st.text_input(label="Kode Captcha")
            input_button = st.form_submit_button("Masuk")

        # Tombol manual jika captcha tidak terbaca
        if st.button("🔄 Ganti Captcha Baru"):
            st.session_state.login_token = ""
            st.rerun()

        if input_button:
            if not input_captcha:
                st.warning("Harap isi kode captcha.")
                return

            with st.spinner("Memproses login..."):
                try:
                    # Payload harus lengkap sesuai struktur <form> di HTML Unair
                    payload = {
                        "mode": "login",
                        "username": input_nim,
                        "password": input_pw,
                        "csrf_token": st.session_state.login_token,
                        "captcha": input_captcha
                    }
                    
                    # Login POST (HANYA SEKALI)
                    login_resp = session.post(f"{base_url}login.php", data=payload)
                    
                    # Cek apakah login berhasil
                    if "Histori Nilai" in login_resp.text or "Biodata" in login_resp.text:
                        # Identifikasi URL (Mahasiswa vs Alumni)
                        trans_url = f"{base_url}modul/mhs/akademik-transkrip.php"
                        if "Alumni" in login_resp.text or input_nim.startswith("A"):
                            trans_url = f"{base_url}modul/alumni/akademik-transkrip.php"
                        
                        # Ambil data transkrip
                        transkrip_resp = session.get(trans_url)

                        if "Histori Nilai" in transkrip_resp.text:
                            soup = BeautifulSoup(transkrip_resp.text, "html.parser")
                            tables = soup.find_all("table")

                            # --- LOGIKA EKSTRAKSI AKUN YANG DIPERBARUI ---
                            user_info = {}
                            info_table = None
                            for table in tables:
                                # Cari tabel yang kemungkinan besar berisi info mahasiswa
                                if "NAMA" in table.get_text().upper() and "NIM" in table.get_text().upper():
                                    info_table = table
                                    break

                            if info_table:
                                rows = info_table.find_all("tr")
                                for row in rows:
                                    cols = row.find_all("td")
                                    # Loop melalui setiap sel untuk mencari kunci informasi
                                    for i, col in enumerate(cols):
                                        key = col.get_text(strip=True)
                                        # Periksa apakah ini adalah kunci yang kita cari
                                        if "Nama" in key and i + 1 < len(cols):
                                            value = cols[i + 1].get_text(strip=True)
                                            # Bersihkan nilai dari karakter ':'
                                            if value.startswith(":"):
                                                value = value[1:].strip()
                                            user_info["Nama Lengkap"] = value

                                        if "NIM" in key and i + 1 < len(cols):
                                            value = cols[i + 1].get_text(strip=True)
                                            if value.startswith(":"):
                                                value = value[1:].strip()
                                            user_info["NIM"] = value

                            st.session_state.user_info = user_info

                            def table_has_keywords(table, keywords=("SEMESTER", "NAMA MATA AJAR", "NILAI")):
                                text = " ".join(th.get_text(" ", strip=True).upper() for th in table.find_all(["th", "td"])[:10])
                                return any(k in text for k in keywords)

                            target_idx = None
                            for i, table in enumerate(tables):
                                if table_has_keywords(table):
                                    target_idx = i
                                    break

                            if target_idx is None:
                                st.error("Tabel nilai tidak ditemukan.")
                                return

                            target = tables[target_idx]
                            rows = target.find_all("tr")

                            data = []
                            for row in rows:
                                cols = row.find_all(["th", "td"])
                                text_cols = [c.get_text(" ", strip=True) for c in cols]
                                if any(cell.strip() for cell in text_cols):
                                    data.append(text_cols)

                            header = data[0]
                            data_rows = data[1:]

                            def semester_key(semester_str):
                                if not semester_str or "/" not in semester_str:
                                    return (0, 0)
                                try:
                                    tahun_awal = int(semester_str.split("/")[0].strip())
                                except ValueError:
                                    tahun_awal = 0
                                jenis = "Ganjil" if "Ganjil" in semester_str else "Genap"
                                urutan = 0 if jenis == "Ganjil" else 1
                                return (tahun_awal, urutan)

                            data_rows.sort(key=lambda r: semester_key(r[0]))

                            wb = Workbook()
                            ws = wb.active
                            ws.title = "Transkrip Nilai"
                            ws.append(header)
                            for row in data_rows[3:]:
                                ws.append(row)

                            excel_buffer = BytesIO()
                            wb.save(excel_buffer)
                            excel_buffer.seek(0)

                            st.session_state.df = pd.read_excel(excel_buffer)
                            st.session_state.logged_in = True
                            st.success("Login berhasil!")
                            st.rerun()

                        else:
                            st.error("Gagal menarik data transkrip. Sesi mungkin berakhir.")
                    else:
                        # Jika gagal, tampilkan alasan (jika ada di HTML)
                        soup_err = BeautifulSoup(login_resp.text, "html.parser")
                        err_msg = soup_err.find("div", {"style": "color: red;"}) # Cek tag error di HTML
                        msg = err_msg.get_text() if err_msg else "NIM, Password, atau Captcha Salah."
                        
                        st.error(f"Login Gagal: {msg}")
                        # Jangan rerun otomatis agar user bisa melihat pesan errornya
                except requests.exceptions.RequestException as e:
                    st.error(f"Terjadi kesalahan koneksi: {e}")



# --- Inisialisasi session state ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "df" not in st.session_state:
    st.session_state.df = None
# Inisialisasi kunci untuk fitur reset
if "grid_key_counter" not in st.session_state:
    st.session_state.grid_key_counter = 0

# --- Router utama ---
if not st.session_state.logged_in:
    display_login_form()
else:
    display_main_app()
