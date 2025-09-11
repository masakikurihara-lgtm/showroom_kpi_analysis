import streamlit as st
import pandas as pd
import numpy as np
import io
import requests
import json
from datetime import datetime, date, timedelta
import pytz
import plotly.graph_objects as go
import plotly.express as px
import time
from bs4 import BeautifulSoup


# ページ設定
st.set_page_config(
    page_title="SHOWROOM ライバーKPI分析ツール",
    page_icon="📊",
    layout="wide"
)

# タイトル
st.markdown(
    "<h1 style='font-size:28px; text-align:center; color:#1f2937;'>SHOWROOM ライバーKPI分析ツール</h1>",
    unsafe_allow_html=True
)

# 説明文
st.markdown(
    "<p style='font-size:16px; text-align:center; color:#4b5563;'>",
    unsafe_allow_html=True
)

st.markdown("---")


# --- 関数定義 ---
@st.cache_data(ttl=60) # キャッシュ保持を60秒に変更
def fetch_event_data():
    """イベントデータをCSVから読み込み、キャッシュする"""
    try:
        event_url = "https://mksoul-pro.com/showroom/file/sr-event-entry.csv"
        event_df = pd.read_csv(event_url)
        event_df.columns = [col.strip() for col in event_df.columns]
        return event_df
    except Exception as e:
        st.error(f"イベントデータの取得に失敗しました: {e}")
        return pd.DataFrame()

# データの読み込みと前処理関数
# @st.cache_data(ttl=3600) # データのキャッシュを1時間保持
def load_and_preprocess_data(account_id, start_date, end_date):
    if not account_id:
        st.error("アカウントIDを入力してください。")
        return None, None, None, None
    
    if start_date > end_date:
        st.error("開始日は終了日より前の日付を選択してください。")
        return None, None, None, None

    loop_start_date = start_date.date() if isinstance(start_date, (datetime, pd.Timestamp)) else start_date
    loop_end_date = end_date.date() if isinstance(end_date, (datetime, pd.Timestamp)) else end_date

    mksp_dfs = []
    df_temp = pd.DataFrame()
    room_id_temp = None
    room_name_temp = None
    
    # 読み込み対象の月をリストアップ
    target_months = []
    current_date_loop = loop_start_date
    while current_date_loop <= loop_end_date:
        target_months.append(current_date_loop)
        if current_date_loop.month == 12:
            current_date_loop = date(current_date_loop.year + 1, 1, 1)
        else:
            current_date_loop = date(current_date_loop.year, current_date_loop.month + 1, 1)
    
    total_months = len(target_months)

    # プログレスバーを一本で実装
    progress_bar = st.progress(0)
    progress_text = st.empty()
    
    # 全体データ(mksp)と個人データを分ける
    is_mksp = account_id == "mksp"

    # 全体データ(mksp)の読み込み
    for i, current_date in enumerate(target_months):
        year = current_date.year
        month = current_date.month
        
        # プログレスバーの進捗計算
        # 個人データの場合は2つのループがあるので、進捗を分けて計算
        if not is_mksp:
            progress = (i + 1) / (total_months * 2)
        else:
            progress = (i + 1) / total_months
        
        progress_bar.progress(progress)
        progress_text.text(f"📊 全体データ ({year}年{month}月) を取得中... ({i+1}/{total_months})")

        url = f"https://mksoul-pro.com/showroom/csv/{year:04d}-{month:02d}_all_all.csv"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            csv_data = io.StringIO(response.content.decode('utf-8-sig'))
            df = pd.read_csv(csv_data, on_bad_lines='skip')
            df.columns = df.columns.str.strip().str.replace('"', '')
            mksp_dfs.append(df)
        
        except requests.exceptions.RequestException as e:
            if e.response and e.response.status_code == 404:
                # st.warning(f"⚠️ {year}年{month}月のデータが見つかりませんでした。スキップします。")
                pass
            else:
                st.error(f"❌ データの取得中に予期せぬエラーが発生しました: {e}")
                progress_bar.empty()
                progress_text.empty()
                return None, None, None, None
        except Exception as e:
            st.error(f"❌ CSVファイルの処理中に予期せぬエラーが発生しました。詳細: {e}")
            progress_bar.empty()
            progress_text.empty()
            return None, None, None, None
            
    if not mksp_dfs:
        st.error(f"選択された期間のデータが一つも見つかりませんでした。")
        progress_bar.empty()
        progress_text.empty()
        return None, None, None, None

    combined_mksp_df = pd.concat(mksp_dfs, ignore_index=True)
    if "配信日時" not in combined_mksp_df.columns:
        raise KeyError("CSVファイルに '配信日時' 列が見つかりませんでした。")
    combined_mksp_df["配信日時"] = pd.to_datetime(combined_mksp_df["配信日時"])

    mksp_df_temp = combined_mksp_df.copy()

    # 個別アカウントIDの読み込み（mkspではない場合のみ）
    if not is_mksp:
        individual_dfs = []
        for i, current_date in enumerate(target_months):
            year = current_date.year
            month = current_date.month
            
            # 個人データ読み込み時のプログレス計算
            progress = (total_months + i + 1) / (total_months * 2)
            
            progress_bar.progress(progress)
            progress_text.text(f"👤 個人データ ({year}年{month}月) を取得中... ({i+1}/{total_months})")
            
            url = f"https://mksoul-pro.com/showroom/csv/{year:04d}-{month:02d}_all_all.csv"
            
            try:
                response = requests.get(url)
                response.raise_for_status()
                csv_data = io.StringIO(response.content.decode('utf-8-sig'))
                df = pd.read_csv(csv_data, on_bad_lines='skip')
                df.columns = df.columns.str.strip().str.replace('"', '')
                individual_dfs.append(df)
            
            except requests.exceptions.RequestException as e:
                if e.response and e.response.status_code == 404:
                    # st.warning(f"⚠️ {year}年{month}月のデータが見つかりませんでした。スキップします。")
                    pass
                else:
                    st.error(f"❌ データの取得中に予期せぬエラーが発生しました: {e}")
                    progress_bar.empty()
                    progress_text.empty()
                    return None, None, None, None
            except Exception as e:
                st.error(f"❌ CSVファイルの処理中に予期せぬエラーが発生しました。詳細: {e}")
                progress_bar.empty()
                progress_text.empty()
                return None, None, None, None

        if not individual_dfs:
            st.warning(f"指定されたアカウントID（{account_id}）のデータが選択された期間に見つかりませんでした。")
            progress_bar.empty()
            progress_text.empty()
            return None, None, None, None
            
        individual_combined_df = pd.concat(individual_dfs, ignore_index=True)
        if "配信日時" not in individual_combined_df.columns:
            raise KeyError("CSVファイルに '配信日時' 列が見つかりませんでした。")
        individual_combined_df["配信日時"] = pd.to_datetime(individual_combined_df["配信日時"])

        filtered_by_account_df = individual_combined_df[individual_combined_df["アカウントID"] == account_id].copy()
        
        if isinstance(start_date, (datetime, pd.Timestamp)):
            filtered_df = filtered_by_account_df[
                (filtered_by_account_df["配信日時"] >= start_date) & 
                (filtered_by_account_df["配信日時"] <= end_date)
            ].copy()
        else:
            filtered_df = filtered_by_account_df[
                (filtered_by_account_df["配信日時"].dt.date >= start_date) & 
                (filtered_by_account_df["配信日時"].dt.date <= end_date)
            ].copy()
        
        df_temp = filtered_df.copy()
        if "ルームID" in df_temp.columns and not df_temp.empty:
            room_id_temp = df_temp["ルームID"].iloc[0]
        if "ルーム名" in df_temp.columns and not df_temp.empty:
            room_name_temp = df_temp["ルーム名"].iloc[0]

    # mkspの場合は、mksp_df_tempをそのままdf_tempとして扱う
    else:
        filtered_by_account_df = combined_mksp_df.copy()
        if isinstance(start_date, (datetime, pd.Timestamp)):
            filtered_df = filtered_by_account_df[
                (filtered_by_account_df["配信日時"] >= start_date) & 
                (filtered_by_account_df["配信日時"] <= end_date)
            ].copy()
        else:
            filtered_df = filtered_by_account_df[
                (filtered_by_account_df["配信日時"].dt.date >= start_date) & 
                (filtered_by_account_df["配信日時"].dt.date <= end_date)
            ].copy()
        
        df_temp = filtered_df.copy()
        room_id_temp = None
        room_name_temp = None

    # 数値型に変換する共通処理
    def convert_to_numeric(df):
        if df is None or df.empty:
            return df
        numeric_cols = [
            "合計視聴数", "視聴会員数", "フォロワー数", "獲得支援point", "コメント数",
            "ギフト数", "期限あり/期限なしSG総額", "コメント人数", "初コメント人数",
            "ギフト人数", "初ギフト人数", "フォロワー増減数", "初ルーム来訪者数", "配信時間(分)", "短時間滞在者数",
            "期限あり/期限なしSGのギフティング数", "期限あり/期限なしSGのギフティング人数"
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", "").replace("-", "0"),
                    errors='coerce'
                ).fillna(0)
        return df

    mksp_df_temp = convert_to_numeric(mksp_df_temp)
    df_temp = convert_to_numeric(df_temp)

    # 最終的なプログレスバーとテキストを非表示にする
    progress_bar.empty()
    progress_text.empty()
    
    return mksp_df_temp, df_temp, room_id_temp, room_name_temp

# サイトからルームIDとルーム名を取得する関数
@st.cache_data(ttl=3600)
def fetch_room_info(account_id):
    if not account_id:
        return None, None
    url = f"https://mksoul-pro.com/showroom/{account_id}"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        room_id = None
        room_name = None
        
        # ルームIDをmetaタグから取得
        meta_og_url = soup.find('meta', property='og:url')
        if meta_og_url:
            og_url = meta_og_url['content']
            room_id = og_url.split('/')[-1]
            
        # ルーム名をmetaタグから取得
        meta_og_title = soup.find('meta', property='og:title')
        if meta_og_title:
            room_name = meta_og_title['content'].replace("のプロフィール", "")
            
        if not room_id or not room_name:
            st.warning(f"⚠️ アカウントID '{account_id}' のルーム情報が見つかりませんでした。")
            return None, None
            
        return room_id, room_name
        
    except requests.exceptions.Timeout:
        st.error("❌ リクエストがタイムアウトしました。インターネット接続を確認してください。")
        return None, None
    except requests.exceptions.RequestException as e:
        st.error(f"❌ ルーム情報の取得中にエラーが発生しました: {e}")
        return None, None
    except Exception as e:
        st.error(f"❌ ルーム情報の解析中にエラーが発生しました: {e}")
        return None, None
        
        
# KPI分析関数
def analyze_kpis(df):
    if df is None or df.empty:
        return {}
    
    analysis = {
        "平均獲得支援point": df["獲得支援point"].mean(),
        "平均コメント数": df["コメント数"].mean(),
        "平均フォロワー増減数": df["フォロワー増減数"].mean(),
        "平均初ルーム来訪者数": df["初ルーム来訪者数"].mean(),
        "平均視聴会員数": df["視聴会員数"].mean(),
        "平均配信時間(分)": df["配信時間(分)"].mean(),
        "総配信時間(時間)": df["配信時間(分)"].sum() / 60,
        "平均獲得SG総額": df["期限あり/期限なしSG総額"].mean()
    }
    return analysis

# --- Streamlit UI ---
st.markdown("### アナリティクス設定")

# フォームを使用して入力欄をまとめる
with st.form(key='analysis_form'):
    account_id = st.text_input(
        "アカウントID", 
        placeholder="アカウントIDを入力してください (例:mksp)",
        help="個人の場合はアカウントID、全体データの場合は「mksp」と入力してください。"
    ).strip()

    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "📅 開始日",
            min_value=date(2023, 1, 1),
            max_value=date.today(),
            value=date.today() - timedelta(days=30),
            help="分析を開始する日付を選択してください。"
        )

    with col2:
        end_date = st.date_input(
            "📅 終了日",
            min_value=date(2023, 1, 1),
            max_value=date.today(),
            value=date.today(),
            help="分析を終了する日付を選択してください。"
        )

    st.markdown("---")

    submit_button = st.form_submit_button(label='🚀 分析開始')

if submit_button:
    # データの読み込み
    with st.spinner("データを取得・前処理中..."):
        mksp_df, df, room_id, room_name = load_and_preprocess_data(account_id, start_date, end_date)

    if df is None or mksp_df is None or df.empty:
        st.warning("⚠️ 取得したデータが空です。アカウントIDや期間を見直してください。")
        st.stop()

    st.success("✅ データ取得と前処理が完了しました！")
    
    # 取得したルーム情報を表示
    if room_name:
        st.markdown(f"### 👤 ルーム名: {room_name}")
    if room_id:
        st.markdown(f"### 🆔 ルームID: {room_id}")

    # KPI分析
    st.markdown("---")
    st.markdown("### 📈 主要KPIのサマリー")

    analysis_mksp = analyze_kpis(mksp_df)
    analysis_user = analyze_kpis(df)
    
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        st.metric(
            label="合計獲得支援Point", 
            value=f"{df['獲得支援point'].sum():,.0f} pt",
            delta=f"{df['獲得支援point'].sum() - mksp_df['獲得支援point'].sum():,.0f} pt",
            delta_color="normal"
        )
    with kpi_col2:
        st.metric(
            label="合計視聴会員数",
            value=f"{df['視聴会員数'].sum():,.0f} 人",
            delta=f"{df['視聴会員数'].sum() - mksp_df['視聴会員数'].sum():,.0f} 人",
            delta_color="normal"
        )
    with kpi_col3:
        st.metric(
            label="合計コメント数",
            value=f"{df['コメント数'].sum():,.0f} コメ",
            delta=f"{df['コメント数'].sum() - mksp_df['コメント数'].sum():,.0f} コメ",
            delta_color="normal"
        )
    with kpi_col4:
        st.metric(
            label="総配信時間",
            value=f"{df['配信時間(分)'].sum():,.0f} 分",
            delta=f"{df['配信時間(分)'].sum() - mksp_df['配信時間(分)'].sum():,.0f} 分",
            delta_color="normal"
        )

    # グラフ表示
    st.markdown("---")
    st.markdown("### 📊 期間別KPI推移")
    
    st.line_chart(df.set_index("配信日時")["獲得支援point"])

    st.markdown("---")
    st.markdown("### 🏆 注目すべき配信")
    
    # 注目すべき配信を抽出
    df_sorted_by_points = df.sort_values(by="獲得支援point", ascending=False).head(5)
    
    for index, row in df_sorted_by_points.iterrows():
        st.markdown(
            f"**配信日時:** {row['配信日時'].strftime('%Y-%m-%d %H:%M')}, "
            f"**獲得支援point:** {row['獲得支援point']:,}pt, "
            f"**視聴会員数:** {row['視聴会員数']:,}人"
        )

    st.markdown("---")
    st.markdown("### 🎯 改善すべき指標")

    # 全体データと比較して平均を下回る指標を特定
    user_kpis = df.mean(numeric_only=True)
    mksp_kpis = mksp_df.mean(numeric_only=True)
    
    improvement_points = []
    
    kpi_map = {
        '獲得支援point': '獲得支援ポイント',
        '視聴会員数': '視聴会員数',
        'コメント数': 'コメント数'
    }

    for kpi, name in kpi_map.items():
        if kpi in user_kpis and kpi in mksp_kpis:
            if user_kpis[kpi] < mksp_kpis[kpi]:
                improvement_points.append(f"**{name}:** あなたの平均値 ({user_kpis[kpi]:,.0f}) は、全体平均 ({mksp_kpis[kpi]:,.0f}) を下回っています。")

    if improvement_points:
        for point in improvement_points:
            st.warning(f"⚠️ {point}")
    else:
        st.info("✅ 全体平均を上回る素晴らしいパフォーマンスです！")

    st.markdown("---")
    
    # 各配信データの詳細表示（展開可能）
    st.subheader("📝 配信データ詳細")
    st.dataframe(df)

    # イベントデータの表示
    event_df = fetch_event_data()
    if not event_df.empty:
        st.markdown("---")
        st.subheader("🎉 開催中イベント情報")
        
        # タイムゾーンを日本時間に設定
        jst = pytz.timezone('Asia/Tokyo')
        
        # 'イベント開始日'と'イベント終了日'を日本時間のdatetimeオブジェクトに変換
        event_df['イベント開始日'] = pd.to_datetime(event_df['イベント開始日'], format='%Y/%m/%d %H:%M:%S').dt.tz_localize(jst)
        event_df['イベント終了日'] = pd.to_datetime(event_df['イベント終了日'], format='%Y/%m/%d %H:%M:%S').dt.tz_localize(jst)
        
        # 現在時刻を日本時間で取得
        now = datetime.now(jst)
        
        # 開催中のイベントをフィルタリング
        active_events = event_df[(event_df['イベント開始日'] <= now) & (event_df['イベント終了日'] >= now)]
        
        if not active_events.empty:
            for index, row in active_events.iterrows():
                st.markdown(f"**イベント名:** {row['イベント名']}")
                st.markdown(f"**イベント期間:** {row['イベント開始日'].strftime('%Y/%m/%d %H:%M')} ~ {row['イベント終了日'].strftime('%Y/%m/%d %H:%M')}")
                st.markdown(f"**説明:** {row['イベント概要']}")
                
                # イベント詳細へのリンク
                st.markdown(f"[イベント詳細ページ]({row['イベントURL']})")
                st.markdown("---")
        else:
            st.info("現在、開催中のイベントはありません。")

    # ヒット分析機能
    st.markdown("---")
    st.subheader("🚀 配信ヒット分析")
    
    st.info("以下の指標が平均を大きく上回った配信を自動でピックアップします。")

    if not df.empty:
        # 閾値となる平均値を計算
        avg_viewers = df["合計視聴数"].mean()
        avg_support_points = df["獲得支援point"].mean()
        avg_comments = df["コメント数"].mean()
        avg_followers = df["フォロワー増減数"].mean()
        avg_commenters = df["コメント人数"].mean()
        avg_gifters = df["ギフト人数"].mean()
        avg_sg_total = df["期限あり/期限なしSG総額"].mean()
        avg_sg_gifters = df["期限あり/期限なしSGのギフティング人数"].mean()
        
        hit_df = df.copy()
        hit_df["ヒット項目"] = [[] for _ in range(len(hit_df))]
        
        for index, row in hit_df.iterrows():
            hit_items = []
            if pd.notna(row['合計視聴数']) and row['合計視聴数'] >= avg_viewers * 1.5: hit_items.append('合計視聴数')
            if pd.notna(row['コメント数']) and row['コメント数'] >= avg_comments * 1.5: hit_items.append('コメント数')
            if pd.notna(row['フォロワー増減数']) and row['フォロワー増減数'] >= avg_followers * 1.5: hit_items.append('フォロワー増減数')
            if pd.notna(row['コメント人数']) and row['コメント人数'] >= avg_commenters * 1.5: hit_items.append('コメント人数')
            if pd.notna(row['初ルーム来訪者数']) and row['視聴会員数'] > 0 and (row['初ルーム来訪者数'] / row['視聴会員数']) >= 0.15: hit_items.append('初見訪問者率')
            if pd.notna(row['初コメント人数']) and row['コメント人数'] > 0 and (row['初コメント人数'] / row['コメント人数']) >= 0.10: hit_items.append('初コメント率')
            if pd.notna(row['初ギフト人数']) and row['ギフト人数'] > 0 and (row['初ギフト人数'] / row['ギフト人数']) >= 0.12: hit_items.append('初ギフト率')
            if pd.notna(row['短時間滞在者数']) and row['視聴会員数'] > 0 and (row['短時間滞在者数'] / row['視聴会員数']) <= 0.15: hit_items.append('短時間滞在者率')
            if pd.notna(row['獲得支援point']) and row['獲得支援point'] >= avg_support_points * 2.7: hit_items.append('獲得支援point')
            if pd.notna(row['期限あり/期限なしSG総額']) and row['期限あり/期限なしSG総額'] >= avg_sg_total * 2.7: hit_items.append('SG総額')
            if pd.notna(row['期限あり/期限なしSGのギフティング人数']) and row['期限あり/期限なしSGのギフティング人数'] >= avg_sg_gifters * 2.2: hit_items.append('SGギフト人数')
            if pd.notna(row['ギフト人数']) and row['ギフト人数'] >= avg_gifters * 2.2: hit_items.append('ギフト人数')
            if pd.notna(row['配信時間(分)']) and row['配信時間(分)'] >= df["配信時間(分)"].mean() * 1.5: hit_items.append('長時間配信')

            hit_df.at[index, "ヒット項目"] = hit_items

        hit_streams = hit_df[hit_df["ヒット項目"].apply(lambda x: len(x) > 0)]
        
        if not hit_streams.empty:
            st.markdown("以下の配信は、特定の指標で高いパフォーマンスを記録しました。")
            
            for index, row in hit_streams.iterrows():
                with st.expander(f"**日時: {row['配信日時'].strftime('%Y-%m-%d %H:%M')}**"):
                    st.write("---")
                    st.markdown(f"**獲得支援point:** {row['獲得支援point']:,}pt")
                    st.markdown(f"**合計視聴数:** {row['合計視聴数']:,}人")
                    st.markdown(f"**コメント数:** {row['コメント数']:,}コメ")
                    st.markdown(f"**ヒット項目:** {', '.join(row['ヒット項目'])}")
        else:
            st.info("該当するヒット配信は見つかりませんでした。")
    else:
        st.warning("分析するデータがありません。")
