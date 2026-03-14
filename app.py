import os
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from st_supabase_connection import SupabaseConnection, execute_query

# -----------------------------------------------------------------------------
# Konfigurasi dasar & tema
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Dinkum Sell Price Database",
    layout="wide",
)

# Dark theme sederhana
DARK_BG = "#0d1117"
LIGHT_TEXT = "#e6edf3"
ACCENT_GREEN = "#238636"

st.markdown(
    f"""
    <style>
        .stApp {{
            background-color: {DARK_BG};
            color: {LIGHT_TEXT};
        }}
        .stMarkdown, .stText, .stDataFrame, .stMetric {{
            color: {LIGHT_TEXT} !important;
        }}
        .stButton>button, .stDownloadButton>button {{
            background-color: {ACCENT_GREEN};
            color: white;
            border-radius: 6px;
            border: 1px solid #1a7f3f;
        }}
        .stButton>button:hover, .stDownloadButton>button:hover {{
            background-color: #2ea043;
        }}
        .stSelectbox, .stTextInput, .stNumberInput, .stTextArea {{
            color: {LIGHT_TEXT};
        }}
        .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Load env & koneksi Supabase
# -----------------------------------------------------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error(
        "SUPABASE_URL atau SUPABASE_ANON_KEY tidak ditemukan.\n\n"
        "Pastikan file `.env` berisi kedua variabel tersebut."
    )
    st.stop()

# Koneksi Supabase via st-supabase-connection
try:
    st_supabase = st.connection(
        name="supabase_connection",
        type=SupabaseConnection,
        ttl=None,  # koneksi dicache, query tetap bisa diatur TTL-nya
        url=SUPABASE_URL,
        key=SUPABASE_ANON_KEY,
    )
except Exception as e:
    st.error(f"Gagal membuat koneksi ke Supabase: {e}")
    st.stop()


# -----------------------------------------------------------------------------
# Realtime subscription (INSERT & UPDATE) -> auto rerun
# -----------------------------------------------------------------------------
def init_realtime_subscription():
    """Subscribe ke perubahan tabel dinkum_items (INSERT & UPDATE)."""
    if st.session_state.get("realtime_subscribed"):
        return

    try:
        channel = (
            st_supabase.channel("realtime:dinkum_items")
            .on(
                "postgres_changes",
                {
                    "event": "*",
                    "schema": "public",
                    "table": "dinkum_items",
                },
                lambda payload: st.experimental_rerun(),
            )
            .subscribe()
        )
        st.session_state["realtime_subscribed"] = True
        st.session_state["realtime_channel"] = channel
    except Exception:
        # Realtime opsional; jangan blokir app kalau gagal
        st.warning(
            "Realtime Supabase tidak aktif. "
            "Pastikan Realtime di-enable untuk tabel `dinkum_items` (opsional)."
        )


init_realtime_subscription()

# -----------------------------------------------------------------------------
# Helper: load data dengan cache
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_all_items():
    try:
        response = execute_query(
            st_supabase.table("dinkum_items").select("*"),
            ttl=300,  # cache di sisi konektor juga (boleh 0 kalau mau benar2 live)
        )
        data = response.data or []
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Gagal mengambil data dari Supabase: {e}")
        return pd.DataFrame()


def reset_data_cache_and_rerun():
    fetch_all_items.clear()
    st.experimental_rerun()


# -----------------------------------------------------------------------------
# Layout utama
# -----------------------------------------------------------------------------
st.title("Dinkum Sell Price Database")

st.caption(
    "App pribadi untuk Kevin Bimo dari Jakarta — catat & cari harga jual item "
    "di game Dinkum (dalam Dinks). Semua data diinput manual oleh kamu sendiri."
)

df = fetch_all_items()

# -----------------------------------------------------------------------------
# Quick stats
# -----------------------------------------------------------------------------
col_stats1, col_stats2 = st.columns(2)

total_items = int(df.shape[0]) if not df.empty else 0
col_stats1.metric("Total Item Tersimpan", f"{total_items}")

if not df.empty and "sell_price" in df.columns:
    try:
        df_price = df.copy()
        df_price["sell_price"] = pd.to_numeric(df_price["sell_price"], errors="coerce")
        df_price = df_price.dropna(subset=["sell_price"])
        if not df_price.empty:
            idx_max = df_price["sell_price"].idxmax()
            top_item = df_price.loc[idx_max]
            col_stats2.metric(
                "Item dengan Harga Tertinggi",
                f"{top_item['name']} — {int(top_item['sell_price']):,} Dinks",
            )
        else:
            col_stats2.metric("Item dengan Harga Tertinggi", "-")
    except Exception:
        col_stats2.metric("Item dengan Harga Tertinggi", "-")
else:
    col_stats2.metric("Item dengan Harga Tertinggi", "-")


st.markdown("---")

# -----------------------------------------------------------------------------
# Search, filter, sort
# -----------------------------------------------------------------------------
st.subheader("Daftar Item")

if df.empty:
    st.info("Belum ada data. Tambahkan item pertama kamu di bawah 👇")
else:
    # Pastikan tipe data
    if "updated_at" in df.columns:
        df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")
    if "sell_price" in df.columns:
        df["sell_price"] = pd.to_numeric(df["sell_price"], errors="coerce")

    col_filters = st.columns([2, 1, 1])

    # Search by name (case-insensitive, partial)
    search_query = col_filters[0].text_input(
        "Cari nama item (case-insensitive, partial match)", ""
    )

    # Filter kategori
    CATEGORY_OPTIONS = [
        "Semua",
        "Resources",
        "Farming",
        "Bugs",
        "Fish",
        "Mining",
        "Hunting",
        "Crafted",
        "Other",
    ]
    selected_category = col_filters[1].selectbox(
        "Filter kategori",
        CATEGORY_OPTIONS,
        index=0,
    )

    # Sort
    SORT_OPTIONS = [
        "Nama (A-Z)",
        "Harga Tertinggi",
        "Terbaru (updated_at)",
    ]
    selected_sort = col_filters[2].selectbox(
        "Urutkan berdasarkan",
        SORT_OPTIONS,
        index=0,
    )

    # Apply search filter
    filtered_df = df.copy()
    if search_query.strip():
        mask = filtered_df["name"].str.contains(
            search_query.strip(), case=False, na=False
        )
        filtered_df = filtered_df[mask]

    # Apply category filter
    if selected_category != "Semua":
        filtered_df = filtered_df[filtered_df["category"] == selected_category]

    # Sorting
    if selected_sort == "Nama (A-Z)":
        filtered_df = filtered_df.sort_values("name", ascending=True, na_position="last")
    elif selected_sort == "Harga Tertinggi" and "sell_price" in filtered_df.columns:
        filtered_df = filtered_df.sort_values(
            "sell_price", ascending=False, na_position="last"
        )
    elif selected_sort == "Terbaru (updated_at)" and "updated_at" in filtered_df.columns:
        filtered_df = filtered_df.sort_values(
            "updated_at", ascending=False, na_position="last"
        )

    # Tabel tampilan
    if not filtered_df.empty:
        display_df = filtered_df.copy()

        # Tambahkan kolom display harga dan tanggal
        if "sell_price" in display_df.columns:
            display_df["sell_price_display"] = display_df["sell_price"].apply(
                lambda x: f"{int(x):,} Dinks" if pd.notnull(x) else ""
            )

        if "updated_at" in display_df.columns:
            display_df["updated_at_display"] = display_df["updated_at"].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(x) else ""
            )

        # Urutan & kolom yang ditampilkan
        columns_to_show = [
            "name",
            "sell_price_display",
            "category",
            "source",
            "notes",
            "updated_at_display",
        ]
        existing_cols = [c for c in columns_to_show if c in display_df.columns]
        table_df = display_df[existing_cols].rename(
            columns={
                "name": "Name",
                "sell_price_display": "Sell Price",
                "category": "Category",
                "source": "Source",
                "notes": "Notes",
                "updated_at_display": "Updated At",
            }
        )

        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Tidak ada item yang cocok dengan filter / pencarian saat ini.")

# -----------------------------------------------------------------------------
# Optional: Copy info item (sederhana)
# -----------------------------------------------------------------------------
if not df.empty:
    st.markdown("#### Copy Info Item Cepat (opsional)")
    copy_col1, copy_col2 = st.columns([2, 3])

    with copy_col1:
        item_names_for_copy = df["name"].tolist()
        selected_for_copy = st.selectbox(
            "Pilih item untuk di-copy infonya",
            item_names_for_copy,
            key="copy_item_select",
        )

    with copy_col2:
        if selected_for_copy:
            row_copy = df[df["name"] == selected_for_copy].iloc[0]
            sell_price_val = int(row_copy["sell_price"]) if row_copy["sell_price"] else 0
            info_str = (
                f"Nama: {row_copy['name']}\n"
                f"Harga: {sell_price_val:,} Dinks\n"
                f"Kategori: {row_copy.get('category') or '-'}\n"
                f"Source: {row_copy.get('source') or '-'}\n"
                f"Notes: {row_copy.get('notes') or '-'}"
            )
            st.text_area(
                "Text yang bisa kamu copy manual:",
                value=info_str,
                height=120,
            )

st.markdown("---")

# -----------------------------------------------------------------------------
# Form tambah / update item
# -----------------------------------------------------------------------------
st.subheader("Form Item")

with st.expander("Tambah / Update Item Dinkum", expanded=True):
    mode = st.radio(
        "Mode Form",
        ["Tambah Item Baru", "Update Item Existing"],
        horizontal=True,
    )

    existing_items_df = df.copy() if not df.empty else pd.DataFrame()

    selected_item_row = None
    selected_item_id = None

    if mode == "Update Item Existing":
        if existing_items_df.empty:
            st.warning("Belum ada item untuk di-update. Tambahkan item baru dulu.")
        else:
            item_names = existing_items_df["name"].tolist()
            selected_name_for_update = st.selectbox(
                "Pilih item yang mau di-update",
                item_names,
                key="update_item_select",
            )
            if selected_name_for_update:
                selected_item_row = existing_items_df[
                    existing_items_df["name"] == selected_name_for_update
                ].iloc[0]
                selected_item_id = selected_item_row.get("id")

    # Prefill value jika update
    default_name = ""
    default_sell_price = 0
    default_category = "Resources"
    default_source = ""
    default_notes = ""

    if selected_item_row is not None:
        default_name = selected_item_row.get("name") or ""
        default_sell_price = (
            int(selected_item_row.get("sell_price"))
            if selected_item_row.get("sell_price") is not None
            else 0
        )
        default_category = selected_item_row.get("category") or default_category
        default_source = selected_item_row.get("source") or ""
        default_notes = selected_item_row.get("notes") or ""

    form_col1, form_col2 = st.columns(2)

    with form_col1:
        name_input = st.text_input("Nama Item *", value=default_name)
        sell_price_input = st.number_input(
            "Harga Jual (Dinks) *",
            min_value=0,
            step=10,
            value=default_sell_price,
        )
        category_input = st.selectbox(
            "Kategori",
            [
                "Resources",
                "Farming",
                "Bugs",
                "Fish",
                "Mining",
                "Hunting",
                "Crafted",
                "Other",
            ],
            index=(
                [
                    "Resources",
                    "Farming",
                    "Bugs",
                    "Fish",
                    "Mining",
                    "Hunting",
                    "Crafted",
                    "Other",
                ].index(default_category)
                if default_category
                in [
                    "Resources",
                    "Farming",
                    "Bugs",
                    "Fish",
                    "Mining",
                    "Hunting",
                    "Crafted",
                    "Other",
                ]
                else 0
            ),
        )

    with form_col2:
        source_input = st.text_input("Source / Cara Mendapat *", value=default_source)
        notes_input = st.text_area("Notes (opsional)", value=default_notes, height=100)

    submitted = st.button("Simpan ke Database", use_container_width=True)

    if submitted:
        if not name_input.strip():
            st.error("Nama item wajib diisi.")
        elif sell_price_input < 0:
            st.error("Harga jual tidak boleh negatif.")
        elif not source_input.strip():
            st.error("Source / cara mendapat wajib diisi.")
        elif mode == "Update Item Existing" and selected_item_id is None:
            st.error("Tidak bisa menemukan ID item yang akan di-update.")
        else:
            payload = {
                "name": name_input.strip(),
                "sell_price": int(sell_price_input),
                "category": category_input,
                "source": source_input.strip(),
                "notes": notes_input.strip() if notes_input else None,
                "updated_at": datetime.utcnow().isoformat(),
            }

            try:
                if mode == "Tambah Item Baru":
                    _ = execute_query(
                        st_supabase.table("dinkum_items").insert([payload]),
                        ttl=0,
                    )
                    st.success("Item baru berhasil ditambahkan ke database.")
                else:
                    # Update berdasarkan id
                    _ = execute_query(
                        st_supabase.table("dinkum_items")
                        .update(payload)
                        .eq("id", selected_item_id),
                        ttl=0,
                    )
                    st.success("Item berhasil di-update.")

                reset_data_cache_and_rerun()

            except Exception as e:
                st.error(f"Gagal menyimpan ke Supabase: {e}")

# -----------------------------------------------------------------------------
# Info tambahan
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("##### Catatan")
st.markdown(
    "- App ini hanya mencatat harga jual item ke vendor (tidak spesifik NPC).\n"
    "- Semua data murni dari input kamu sendiri; tidak ada data preset.\n"
    "- Untuk menghapus item, gunakan Table Editor / SQL Editor di dashboard Supabase."
)