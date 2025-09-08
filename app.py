import streamlit as st
import pandas as pd
import numpy as np
import io
import requests
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

# --- ここから変更 ---
# タイトル
st.markdown(
    "<h1 style='font-size:28px; text-align:center; color:#1f2937;'>SHOWROOM ライバーKPI分析ツール</h1>",
    unsafe_allow_html=True
)

# 説明文
st.markdown(
    "<p style='font-size:16px; text-align:center; color:#4b5563;'>"
    "アカウントIDと分析方法を指定して、ライバーのパフォーマンスを分析します。"
    "</p>",
    unsafe_allow_html=True
)

st.markdown("---")


# --- 関数定義 ---
@st.cache_data(ttl=60) # キャッシュ保持を60秒に変更
def fetch_event_data():
    """イベントデータをCSVから読み込み、キャッシュする"""
    try:
        event_url = "https://mksoul-pro.com/showroom/file/sr-event-entry.csv"
        event_df = pd.read_csv(event_url, dtype={'アカウントID': str})
        event_df['開始日時'] = pd.to_datetime(event_df['開始日時'], errors='coerce')
        event_df['終了日時'] = pd.to_datetime(event_df['終了日時'], errors='coerce')
        event_df_filtered = event_df[(event_df['紐付け'] == '○') & event_df['開始日時'].notna() & event_df['終了日時'].notna()].copy()
        event_df_filtered = event_df_filtered.sort_values(by='開始日時', ascending=True)
        return event_df_filtered
    except Exception as e:
        st.warning(f"イベント情報の取得に失敗しました: {e}")
        return pd.DataFrame()

# 入力フィールド
account_id = st.text_input(
    "アカウントID（全体平均等は mksp）",
    ""
)

# 分析方法の選択
analysis_type = st.radio(
    "分析方法を選択",
    ('期間で指定', 'イベントで指定'),
    horizontal=True,
    key='analysis_type_selector'
)

# 日本時間（JST）を明示的に指定
JST = pytz.timezone('Asia/Tokyo')
today = datetime.now(JST).date()

# UI要素の状態を保持する変数を初期化
selected_date_range_val = None
selected_event_val = None

# 条件に応じた入力ウィジェットの表示
if analysis_type == '期間で指定':
    default_end_date = today - timedelta(days=1)
    default_start_date = default_end_date - timedelta(days=30)
    selected_date_range_val = st.date_input(
        "分析期間",
        (default_start_date, default_end_date),
        max_value=today
    )
else:  # 'イベントで指定'
    if account_id:
        event_df = fetch_event_data()
        if not event_df.empty:
            user_events = event_df[event_df['アカウントID'] == account_id].sort_values('開始日時', ascending=False)
            if not user_events.empty:
                event_names = user_events['イベント名'].unique().tolist()
                if event_names:
                    selected_event_val = st.selectbox("分析するイベントを選択", options=event_names)
                else:
                    st.info("このアカウントIDに紐づくイベントはありません。")
            else:
                st.info("このアカウントIDに紐づくイベントデータが見つかりませんでした。")
        else:
            st.warning("イベントデータを取得できませんでした。")
    else:
        st.info("先にアカウントIDを入力してください。")


# ボタンの前に余白を追加
st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
# --- ここまで変更 ---


# データの読み込みと前処理関数
def load_and_preprocess_data(account_id, start_date, end_date):
    if not account_id:
        st.error("アカウントIDを入力してください。")
        return None, None
    
    if start_date > end_date:
        st.error("開始日は終了日より前の日付を選択してください。")
        return None, None

    all_dfs = []
    current_date = start_date
    while current_date <= end_date:
        year = current_date.year
        month = current_date.month
        
        url = f"https://mksoul-pro.com/showroom/csv/{year:04d}-{month:02d}_all_all.csv"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            csv_text = response.content.decode('utf-8-sig')
            lines = csv_text.strip().split('\n')
            header_line = lines[0]
            data_lines = lines[1:]
            cleaned_data_lines = [','.join(line.split(',')[:-1]) for line in data_lines]
            cleaned_csv_text = header_line + '\n' + '\n'.join(cleaned_data_lines)
            csv_data = io.StringIO(cleaned_csv_text)
            df = pd.read_csv(csv_data)
            df.columns = df.columns.str.strip().str.replace('"', '')
            all_dfs.append(df)
            
        except requests.exceptions.RequestException as e:
            st.warning(f"{year}年{month}月のデータが見つかりませんでした。スキップします。")
        except Exception as e:
            st.error(f"CSVファイルの処理中に予期せぬエラーが発生しました。詳細: {e}")
            return None, None
            
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)

    if not all_dfs:
        st.error(f"選択された期間のデータが一つも見つかりませんでした。")
        return None, None

    combined_df = pd.concat(all_dfs, ignore_index=True)

    if "配信日時" not in combined_df.columns:
        raise KeyError("CSVファイルに '配信日時' 列が見つかりませんでした。")
    combined_df["配信日時"] = pd.to_datetime(combined_df["配信日時"])

    if account_id == "mksp":
        filtered_df = combined_df.copy()
    else:
        filtered_df = combined_df[combined_df["アカウントID"] == account_id].copy()
    
    filtered_df = filtered_df[
        (filtered_df["配信日時"].dt.date >= start_date) & 
        (filtered_df["配信日時"].dt.date <= end_date)
    ].copy()

    if filtered_df.empty:
        st.warning(f"指定されたアカウントID（{account_id}）のデータが選択された期間に見つかりませんでした。")
        return None, None

    # 数値型に変換する列のリスト
    numeric_cols = [
        "合計視聴数", "視聴会員数", "フォロワー数", "獲得支援point", "コメント数",
        "ギフト数", "期限あり/期限なしSG総額", "コメント人数", "初コメント人数",
        "ギフト人数", "初ギフト人数", "フォロワー増減数", "初ルーム来訪者数", "配信時間(分)", "短時間滞在者数",
        "期限あり/期限なしSGのギフティング数", "期限あり/期限なしSGのギフティング人数" # 追加した列
    ]

    for col in numeric_cols:
        if col in filtered_df.columns:
            filtered_df[col] = pd.to_numeric(filtered_df[col].astype(str).str.replace(",", "").replace("-", "0"), errors='coerce')

    
    if "ルームID" in filtered_df.columns and not filtered_df.empty:
        room_id = filtered_df["ルームID"].iloc[0]
    else:
        room_id = None
        
    return filtered_df, room_id

def categorize_time_of_day_with_range(hour):
    if 3 <= hour < 6:
        return "早朝 (3-6時)"
    elif 6 <= hour < 9:
        return "朝 (6-9時)"
    elif 9 <= hour < 12:
        return "午前 (9-12時)"
    elif 12 <= hour < 15:
        return "昼 (12-15時)"
    elif 15 <= hour < 18:
        return "午後 (15-18時)"
    elif 18 <= hour < 21:
        return "夜前半 (18-21時)"
    elif 21 <= hour < 22:
        return "夜ピーク (21-22時)"
    elif 22 <= hour < 24:
        return "夜後半 (22-24時)"
    else:
        return "深夜 (0-3時)"

def merge_event_data(df_to_merge, event_df):
    """配信データにイベント名をマージする"""
    if event_df.empty:
        df_to_merge['イベント名'] = ""
        return df_to_merge

    def find_event_name(row):
        account_id = str(row['アカウントID'])
        stream_time = row['配信日時']
        
        matching_events = event_df[
            (event_df['アカウントID'] == account_id) &
            (event_df['開始日時'] <= stream_time) &
            (event_df['終了日時'] >= stream_time)
        ]
        
        if not matching_events.empty:
            return matching_events.iloc[0]['イベント名']
        return ""

    df_to_merge['イベント名'] = df_to_merge.apply(find_event_name, axis=1)
    return df_to_merge


# --- メインロジック ---
if st.button("分析を実行"):
    final_start_date, final_end_date = None, None

    if st.session_state.analysis_type_selector == '期間で指定':
        if selected_date_range_val and len(selected_date_range_val) == 2:
            final_start_date, final_end_date = selected_date_range_val
        else:
            st.error("有効な期間が選択されていません。")
    
    else:  # 'イベントで指定'
        if not account_id:
            st.error("アカウントIDが入力されていません。")
        elif not selected_event_val:
            st.error("分析対象のイベントが選択されていません。")
        else:
            event_df = fetch_event_data()
            event_details = event_df[
                (event_df['アカウントID'] == account_id) & 
                (event_df['イベント名'] == selected_event_val)
            ]
            if not event_details.empty:
                final_start_date = event_details.iloc[0]['開始日時'].date()
                final_end_date = event_details.iloc[0]['終了日時'].date()
            else:
                st.error("選択されたイベントの詳細が見つかりませんでした。")

    if final_start_date and final_end_date:
        st.session_state.run_analysis = True
        st.session_state.start_date = final_start_date
        st.session_state.end_date = final_end_date
    else:
        st.session_state.run_analysis = False


if 'run_analysis' not in st.session_state:
    st.session_state.run_analysis = False

if st.session_state.run_analysis:
    start_date = st.session_state.start_date
    end_date = st.session_state.end_date
        
    # 全体（mksp）のデータを最初に読み込み、計算を一度だけ行う
    mksp_df, _ = load_and_preprocess_data("mksp", start_date, end_date)

    if mksp_df is not None and not mksp_df.empty:
        # MK平均値と中央値を計算してセッションステートに保存
        # 初見訪問者率
        mk_first_time_df = mksp_df.dropna(subset=['初ルーム来訪者数', '合計視聴数'])
        st.session_state.mk_avg_rate_visit = (mk_first_time_df['初ルーム来訪者数'] / mk_first_time_df['合計視聴数']).mean() * 100 if not mk_first_time_df.empty else 0
        st.session_state.mk_median_rate_visit = (mk_first_time_df['初ルーム来訪者数'] / mk_first_time_df['合計視聴数']).median() * 100 if not mk_first_time_df.empty else 0

        # 初コメント率
        mk_comment_df = mksp_df.dropna(subset=['初コメント人数', 'コメント人数'])
        st.session_state.mk_avg_rate_comment = (mk_comment_df['初コメント人数'] / mk_comment_df['コメント人数']).mean() * 100 if not mk_comment_df.empty else 0
        st.session_state.mk_median_rate_comment = (mk_comment_df['初コメント人数'] / mk_comment_df['コメント人数']).median() * 100 if not mk_comment_df.empty else 0
        
        # 初ギフト率
        mk_gift_df = mksp_df.dropna(subset=['初ギフト人数', 'ギフト人数'])
        st.session_state.mk_avg_rate_gift = (mk_gift_df['初ギフト人数'] / mk_gift_df['ギフト人数']).mean() * 100 if not mk_gift_df.empty else 0
        st.session_state.mk_median_rate_gift = (mk_gift_df['初ギフト人数'] / mk_gift_df['ギフト人数']).median() * 100 if not mk_gift_df.empty else 0
        
        # 短時間滞在者率
        mk_short_stay_df = mksp_df.dropna(subset=['短時間滞在者数', '視聴会員数'])
        st.session_state.mk_avg_rate_short_stay = (mk_short_stay_df['短時間滞在者数'] / mk_short_stay_df['視聴会員数']).mean() * 100 if not mk_short_stay_df.empty else 0
        st.session_state.mk_median_rate_short_stay = (mk_short_stay_df['短時間滞在者数'] / mk_short_stay_df['視聴会員数']).median() * 100 if not mk_short_stay_df.empty else 0
        
        # SGギフト数率
        mk_sg_gift_df = mksp_df.dropna(subset=['期限あり/期限なしSGのギフティング数', 'ギフト数'])
        st.session_state.mk_avg_rate_sg_gift = (mk_sg_gift_df['期限あり/期限なしSGのギフティング数'] / mk_sg_gift_df['ギフト数']).mean() * 100 if not mk_sg_gift_df.empty else 0
        st.session_state.mk_median_rate_sg_gift = (mk_sg_gift_df['期限あり/期限なしSGのギフティング数'] / mk_sg_gift_df['ギフト数']).median() * 100 if not mk_sg_gift_df.empty else 0

        # SGギフト人数率
        mk_sg_person_df = mksp_df.dropna(subset=['期限あり/期限なしSGのギフティング人数', 'ギフト人数'])
        st.session_state.mk_avg_rate_sg_person = (mk_sg_person_df['期限あり/期限なしSGのギフティング人数'] / mk_sg_person_df['ギフト人数']).mean() * 100 if not mk_sg_person_df.empty else 0
        st.session_state.mk_median_rate_sg_person = (mk_sg_person_df['期限あり/期限なしSGのギフティング人数'] / mk_sg_person_df['ギフト人数']).median() * 100 if not mk_sg_person_df.empty else 0

    # ライバー個別のデータ読み込み
    df, room_id = load_and_preprocess_data(account_id, start_date, end_date)
    
    if df is not None and not df.empty:
        st.success("データの読み込みが完了しました！")
        
        if account_id == "mksp":
            st.subheader("💡 全ライバーの集計データ")
            st.info("このビューでは、個人関連データは表示されません。")
            
            total_support_points = int(df["獲得支援point"].sum())
            total_viewers = int(df["合計視聴数"].sum())
            total_comments = int(df["コメント数"].sum())
            
            st.markdown(f"**合計獲得支援ポイント:** {total_support_points:,} pt")
            st.markdown(f"**合計視聴数:** {total_viewers:,} 人")
            st.markdown(f"**合計コメント数:** {total_comments:,} 件")

            st.subheader("📊 時間帯別パフォーマンス分析 (平均値)")
            st.info("※ このグラフは、各時間帯に配信した際の各KPIの**平均値**を示しています。棒上の数字は、その時間帯の配信件数です。")
            
            df['時間帯'] = df['配信日時'].dt.hour.apply(categorize_time_of_day_with_range)
            
            time_of_day_kpis_mean = df.groupby('時間帯').agg({
                '獲得支援point': 'mean',
                '合計視聴数': 'mean',
                'コメント数': 'mean'
            }).reset_index()

            time_of_day_order = [
                "深夜 (0-3時)", "早朝 (3-6時)", "朝 (6-9時)", "午前 (9-12時)", 
                "昼 (12-15時)", "午後 (15-18時)", "夜前半 (18-21時)", 
                "夜ピーク (21-22時)", "夜後半 (22-24時)"
            ]
            time_of_day_kpis_mean['時間帯'] = pd.Categorical(time_of_day_kpis_mean['時間帯'], categories=time_of_day_order, ordered=True)
            time_of_day_kpis_mean = time_of_day_kpis_mean.sort_values('時間帯')
            
            time_of_day_counts = df['時間帯'].value_counts().reindex(time_of_day_order, fill_value=0)

            col1, col2, col3 = st.columns(3)

            with col1:
                fig1 = go.Figure(go.Bar(
                    x=time_of_day_kpis_mean['時間帯'],
                    y=time_of_day_kpis_mean['獲得支援point'],
                    text=time_of_day_counts.loc[time_of_day_kpis_mean['時間帯']],
                    textposition='auto',
                    marker_color='#1f77b4',
                    name='獲得支援point'
                ))
                fig1.update_layout(
                    title_text="獲得支援point",
                    title_font_size=16,
                    yaxis=dict(title="獲得支援point", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                fig2 = go.Figure(go.Bar(
                    x=time_of_day_kpis_mean['時間帯'],
                    y=time_of_day_kpis_mean['合計視聴数'],
                    text=time_of_day_counts.loc[time_of_day_kpis_mean['時間帯']],
                    textposition='auto',
                    marker_color='#ff7f0e',
                    name='合計視聴数'
                ))
                fig2.update_layout(
                    title_text="合計視聴数",
                    title_font_size=16,
                    yaxis=dict(title="合計視聴数", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig2, use_container_width=True)

            with col3:
                fig3 = go.Figure(go.Bar(
                    x=time_of_day_kpis_mean['時間帯'],
                    y=time_of_day_kpis_mean['コメント数'],
                    text=time_of_day_counts.loc[time_of_day_kpis_mean['時間帯']],
                    textposition='auto',
                    marker_color='#2ca02c',
                    name='コメント数'
                ))
                fig3.update_layout(
                    title_text="コメント数",
                    title_font_size=16,
                    yaxis=dict(title="コメント数", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig3, use_container_width=True)

            st.subheader("📊 時間帯別パフォーマンス分析 (中央値)")
            st.info("※ このグラフは、各時間帯に配信した際の各KPIの**中央値**を示しています。突出した値の影響を受けにくく、一般的な傾向を把握するのに役立ちます。棒上の数字は、その時間帯の配信件数です。")
            
            time_of_day_kpis_median = df.groupby('時間帯').agg({
                '獲得支援point': 'median',
                '合計視聴数': 'median',
                'コメント数': 'median'
            }).reset_index()

            time_of_day_kpis_median['時間帯'] = pd.Categorical(time_of_day_kpis_median['時間帯'], categories=time_of_day_order, ordered=True)
            time_of_day_kpis_median = time_of_day_kpis_median.sort_values('時間帯')
            
            col4, col5, col6 = st.columns(3)
            
            with col4:
                fig4 = go.Figure(go.Bar(
                    x=time_of_day_kpis_median['時間帯'],
                    y=time_of_day_kpis_median['獲得支援point'],
                    text=time_of_day_counts.loc[time_of_day_kpis_median['時間帯']],
                    textposition='auto',
                    marker_color='#1f77b4',
                    name='獲得支援point'
                ))
                fig4.update_layout(
                    title_text="獲得支援point (中央値)",
                    title_font_size=16,
                    yaxis=dict(title="獲得支援point", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig4, use_container_width=True)
            
            with col5:
                fig5 = go.Figure(go.Bar(
                    x=time_of_day_kpis_median['時間帯'],
                    y=time_of_day_kpis_median['合計視聴数'],
                    text=time_of_day_counts.loc[time_of_day_kpis_median['時間帯']],
                    textposition='auto',
                    marker_color='#ff7f0e',
                    name='合計視聴数'
                ))
                fig5.update_layout(
                    title_text="合計視聴数 (中央値)",
                    title_font_size=16,
                    yaxis=dict(title="合計視聴数", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig5, use_container_width=True)

            with col6:
                fig6 = go.Figure(go.Bar(
                    x=time_of_day_kpis_median['時間帯'],
                    y=time_of_day_kpis_median['コメント数'],
                    text=time_of_day_counts.loc[time_of_day_kpis_median['時間帯']],
                    textposition='auto',
                    marker_color='#2ca02c',
                    name='コメント数'
                ))
                fig6.update_layout(
                    title_text="コメント数 (中央値)",
                    title_font_size=16,
                    yaxis=dict(title="コメント数", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig6, use_container_width=True)
            
        else: # 個別アカウントIDの場合
            st.subheader("📈 主要KPIの推移")
            df_sorted_asc = df.sort_values(by="配信日時", ascending=True).copy()
            
            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=df_sorted_asc["配信日時"],
                y=df_sorted_asc["獲得支援point"],
                name="獲得支援point",
                mode='lines+markers',
                marker=dict(symbol='circle')
            ))

            fig.add_trace(go.Scatter(
                x=df_sorted_asc["配信日時"],
                y=df_sorted_asc["配信時間(分)"],
                name="配信時間(分)",
                mode='lines+markers',
                yaxis="y2",
                marker=dict(symbol='square')
            ))
            fig.add_trace(go.Scatter(
                x=df_sorted_asc["配信日時"],
                y=df_sorted_asc["合計視聴数"],
                name="合計視聴数",
                mode='lines+markers',
                yaxis="y2",
                marker=dict(symbol='star')
            ))

            fig.update_layout(
                title="KPIの推移（配信時間別）",
                xaxis=dict(title="配信日時"),
                yaxis=dict(title="獲得支援point", side="left", showgrid=False),
                yaxis2=dict(title="配信時間・視聴数", overlaying="y", side="right"),
                legend=dict(x=0, y=1.1, orientation="h"),
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("📊 時間帯別パフォーマンス分析 (平均値)")
            st.info("※ このグラフは、各時間帯に配信した際の各KPIの**平均値**を示しています。棒上の数字は、その時間帯の配信件数です。")
            
            df['時間帯'] = df['配信日時'].dt.hour.apply(categorize_time_of_day_with_range)
            
            time_of_day_kpis_mean = df.groupby('時間帯').agg({
                '獲得支援point': 'mean',
                '合計視聴数': 'mean',
                'コメント数': 'mean'
            }).reset_index()

            time_of_day_order = [
                "深夜 (0-3時)", "早朝 (3-6時)", "朝 (6-9時)", "午前 (9-12時)", 
                "昼 (12-15時)", "午後 (15-18時)", "夜前半 (18-21時)", 
                "夜ピーク (21-22時)", "夜後半 (22-24時)"
            ]
            time_of_day_kpis_mean['時間帯'] = pd.Categorical(time_of_day_kpis_mean['時間帯'], categories=time_of_day_order, ordered=True)
            time_of_day_kpis_mean = time_of_day_kpis_mean.sort_values('時間帯')
            
            time_of_day_counts = df['時間帯'].value_counts().reindex(time_of_day_order, fill_value=0)

            col1, col2, col3 = st.columns(3)

            with col1:
                fig1 = go.Figure(go.Bar(
                    x=time_of_day_kpis_mean['時間帯'],
                    y=time_of_day_kpis_mean['獲得支援point'],
                    text=time_of_day_counts.loc[time_of_day_kpis_mean['時間帯']],
                    textposition='auto',
                    marker_color='#1f77b4',
                    name='獲得支援point'
                ))
                fig1.update_layout(
                    title_text="獲得支援point",
                    title_font_size=16,
                    yaxis=dict(title="獲得支援point", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                fig2 = go.Figure(go.Bar(
                    x=time_of_day_kpis_mean['時間帯'],
                    y=time_of_day_kpis_mean['合計視聴数'],
                    text=time_of_day_counts.loc[time_of_day_kpis_mean['時間帯']],
                    textposition='auto',
                    marker_color='#ff7f0e',
                    name='合計視聴数'
                ))
                fig2.update_layout(
                    title_text="合計視聴数",
                    title_font_size=16,
                    yaxis=dict(title="合計視聴数", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig2, use_container_width=True)

            with col3:
                fig3 = go.Figure(go.Bar(
                    x=time_of_day_kpis_mean['時間帯'],
                    y=time_of_day_kpis_mean['コメント数'],
                    text=time_of_day_counts.loc[time_of_day_kpis_mean['時間帯']],
                    textposition='auto',
                    marker_color='#2ca02c',
                    name='コメント数'
                ))
                fig3.update_layout(
                    title_text="コメント数",
                    title_font_size=16,
                    yaxis=dict(title="コメント数", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig3, use_container_width=True)

            st.subheader("📊 時間帯別パフォーマンス分析 (中央値)")
            st.info("※ このグラフは、各時間帯に配信した際の各KPIの**中央値**を示しています。突出した値の影響を受けにくく、一般的な傾向を把握するのに役立ちます。棒上の数字は、その時間帯の配信件数です。")
            
            time_of_day_kpis_median = df.groupby('時間帯').agg({
                '獲得支援point': 'median',
                '合計視聴数': 'median',
                'コメント数': 'median'
            }).reset_index()

            time_of_day_kpis_median['時間帯'] = pd.Categorical(time_of_day_kpis_median['時間帯'], categories=time_of_day_order, ordered=True)
            time_of_day_kpis_median = time_of_day_kpis_median.sort_values('時間帯')
            
            col4, col5, col6 = st.columns(3)
            
            with col4:
                fig4 = go.Figure(go.Bar(
                    x=time_of_day_kpis_median['時間帯'],
                    y=time_of_day_kpis_median['獲得支援point'],
                    text=time_of_day_counts.loc[time_of_day_kpis_median['時間帯']],
                    textposition='auto',
                    marker_color='#1f77b4',
                    name='獲得支援point'
                ))
                fig4.update_layout(
                    title_text="獲得支援point (中央値)",
                    title_font_size=16,
                    yaxis=dict(title="獲得支援point", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig4, use_container_width=True)
            
            with col5:
                fig5 = go.Figure(go.Bar(
                    x=time_of_day_kpis_median['時間帯'],
                    y=time_of_day_kpis_median['合計視聴数'],
                    text=time_of_day_counts.loc[time_of_day_kpis_median['時間帯']],
                    textposition='auto',
                    marker_color='#ff7f0e',
                    name='合計視聴数'
                ))
                fig5.update_layout(
                    title_text="合計視聴数 (中央値)",
                    title_font_size=16,
                    yaxis=dict(title="合計視聴数", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig5, use_container_width=True)

            with col6:
                fig6 = go.Figure(go.Bar(
                    x=time_of_day_kpis_median['時間帯'],
                    y=time_of_day_kpis_median['コメント数'],
                    text=time_of_day_counts.loc[time_of_day_kpis_median['時間帯']],
                    textposition='auto',
                    marker_color='#2ca02c',
                    name='コメント数'
                ))
                fig6.update_layout(
                    title_text="コメント数 (中央値)",
                    title_font_size=16,
                    yaxis=dict(title="コメント数", title_font_size=14),
                    font=dict(size=12),
                    height=400,
                    margin=dict(t=50, b=0, l=40, r=40)
                )
                st.plotly_chart(fig6, use_container_width=True)
            
            st.subheader("📝 配信ごとの詳細データ")
            
            df_display = df.sort_values(by="配信日時", ascending=False).copy()
            
            # イベントデータを取得してマージ
            event_df_master = fetch_event_data()
            df_display = merge_event_data(df_display, event_df_master)

            st.dataframe(df_display, hide_index=True)
            st.caption("※一部イベントのみイベント名に反映しています。")
            
            st.subheader("📝 全体サマリー")
            total_support_points = int(df_display["獲得支援point"].sum())
            if "フォロワー数" in df_display.columns and not df_display.empty:
                df_sorted_by_date = df_display.sort_values(by="配信日時")
                if not df_sorted_by_date.empty:
                    final_followers = int(df_sorted_by_date["フォロワー数"].iloc[-1])
                    initial_followers = int(df_sorted_by_date["フォロワー数"].iloc[0])
                    total_follower_increase = final_followers - initial_followers
                    st.markdown(f"**フォロワー純増数:** {total_follower_increase:,} 人")
                    st.markdown(f"**最終フォロワー数:** {final_followers:,} 人")
            
            st.markdown(f"**合計獲得支援ポイント:** {total_support_points:,} pt")

            st.subheader("📊 その他数値分析")
            
            row1_col1, row1_col2, row1_col3 = st.columns(3)
            row2_col1, row2_col2, row2_col3 = st.columns(3)
            
            metric_html_style = """
            <style>
                .stMetric-container {
                    background-color: transparent;
                    border: none;
                    padding-bottom: 20px;
                }
                .metric-label { font-size: 16px; font-weight: 600; color: #000000; margin-bottom: -5px; }
                .metric-value { font-size: 32px; font-weight: bold; color: #1f77b4; }
                .metric-caption { font-size: 12px; color: #a0a0a0; margin-top: -5px; }
                .metric-help { font-size: 12px; color: #808080; margin-top: 10px; line-height: 1.5; }
            </style>
            """
            st.markdown(metric_html_style, unsafe_allow_html=True)
            
            with row1_col1:
                first_time_df = df_display.dropna(subset=['初ルーム来訪者数', '合計視聴数'])
                total_members_for_first_time = first_time_df["合計視聴数"].sum()
                first_time_visitors = first_time_df["初ルーム来訪者数"].sum()
                first_time_rate = f"{first_time_visitors / total_members_for_first_time * 100:.1f}%" if total_members_for_first_time > 0 else "0%"
                metric_html = f"""
                <div class="stMetric-container">
                    <div class="metric-label">初見訪問者率</div><div class="metric-value">{first_time_rate}</div>
                    <div class="metric-caption">（MK平均値：{st.session_state.get('mk_avg_rate_visit', 0):.1f}% / MK中央値：{st.session_state.get('mk_median_rate_visit', 0):.1f}%）</div>
                    <div class="metric-help">合計視聴数に対する初ルーム来訪者数の割合です。</div>
                </div>"""
                st.markdown(metric_html, unsafe_allow_html=True)
            
            with row1_col2:
                comment_df = df_display.dropna(subset=['初コメント人数', 'コメント人数'])
                total_commenters = comment_df["コメント人数"].sum()
                first_time_commenters = comment_df["初コメント人数"].sum()
                first_comment_rate = f"{first_time_commenters / total_commenters * 100:.1f}%" if total_commenters > 0 else "0%"
                metric_html = f"""
                <div class="stMetric-container">
                    <div class="metric-label">初コメント率</div><div class="metric-value">{first_comment_rate}</div>
                    <div class="metric-caption">（MK平均値：{st.session_state.get('mk_avg_rate_comment', 0):.1f}% / MK中央値：{st.session_state.get('mk_median_rate_comment', 0):.1f}%）</div>
                    <div class="metric-help">合計コメント人数に対する初コメント会員数の割合です。</div>
                </div>"""
                st.markdown(metric_html, unsafe_allow_html=True)

            with row1_col3:
                gift_df = df_display.dropna(subset=['初ギフト人数', 'ギフト人数'])
                total_gifters = gift_df["ギフト人数"].sum()
                first_time_gifters = gift_df["初ギフト人数"].sum()
                first_gift_rate = f"{first_time_gifters / total_gifters * 100:.1f}%" if total_gifters > 0 else "0%"
                metric_html = f"""
                <div class="stMetric-container">
                    <div class="metric-label">初ギフト率</div><div class="metric-value">{first_gift_rate}</div>
                    <div class="metric-caption">（MK平均値：{st.session_state.get('mk_avg_rate_gift', 0):.1f}% / MK中央値：{st.session_state.get('mk_median_rate_gift', 0):.1f}%）</div>
                    <div class="metric-help">合計ギフト会員数に対する初ギフト会員数の割合です。</div>
                </div>"""
                st.markdown(metric_html, unsafe_allow_html=True)

            with row2_col1:
                short_stay_df = df_display.dropna(subset=['短時間滞在者数', '視聴会員数'])
                total_viewers_for_short_stay = short_stay_df["視聴会員数"].sum()
                short_stay_visitors = short_stay_df["短時間滞在者数"].sum()
                short_stay_rate = f"{short_stay_visitors / total_viewers_for_short_stay * 100:.1f}%" if total_viewers_for_short_stay > 0 else "0%"
                metric_html = f"""
                <div class="stMetric-container">
                    <div class="metric-label">短時間滞在者率</div><div class="metric-value">{short_stay_rate}</div>
                    <div class="metric-caption">（MK平均値：{st.session_state.get('mk_avg_rate_short_stay', 0):.1f}% / MK中央値：{st.session_state.get('mk_median_rate_short_stay', 0):.1f}%）</div>
                    <div class="metric-help">視聴会員数に対する滞在時間が1分未満の会員数の割合です。</div>
                </div>"""
                st.markdown(metric_html, unsafe_allow_html=True)
                
            with row2_col2:
                sg_gift_df = df_display.dropna(subset=['期限あり/期限なしSGのギフティング数', 'ギフト数'])
                total_gifts = sg_gift_df["ギフト数"].sum()
                total_sg_gifts = sg_gift_df["期限あり/期限なしSGのギフティング数"].sum()
                sg_gift_rate = f"{total_sg_gifts / total_gifts * 100:.1f}%" if total_gifts > 0 else "0%"
                metric_html = f"""
                <div class="stMetric-container">
                    <div class="metric-label">SGギフト数率</div><div class="metric-value">{sg_gift_rate}</div>
                    <div class="metric-caption">（MK平均値：{st.session_state.get('mk_avg_rate_sg_gift', 0):.1f}% / MK中央値：{st.session_state.get('mk_median_rate_sg_gift', 0):.1f}%）</div>
                    <div class="metric-help">ギフト総数に対するSGギフト数の割合です。</div>
                </div>"""
                st.markdown(metric_html, unsafe_allow_html=True)

            with row2_col3:
                sg_person_df = df_display.dropna(subset=['期限あり/期限なしSGのギフティング人数', 'ギフト人数'])
                total_gifters = sg_person_df["ギフト人数"].sum()
                total_sg_gifters = sg_person_df["期限あり/期限なしSGのギフティング人数"].sum()
                sg_person_rate = f"{total_sg_gifters / total_gifters * 100:.1f}%" if total_gifters > 0 else "0%"
                metric_html = f"""
                <div class="stMetric-container">
                    <div class="metric-label">SGギフト人数率</div><div class="metric-value">{sg_person_rate}</div>
                    <div class="metric-caption">（MK平均値：{st.session_state.get('mk_avg_rate_sg_person', 0):.1f}% / MK中央値：{st.session_state.get('mk_median_rate_sg_person', 0):.1f}%）</div>
                    <div class="metric-help">ギフト人数総数に対するSGギフト人数の割合です。</div>
                </div>"""
                st.markdown(metric_html, unsafe_allow_html=True)

            st.markdown("<hr>", unsafe_allow_html=True)

            st.subheader("🎯 ヒット配信")
            st.info("特定の条件を満たしたパフォーマンスの高い配信をピックアップしています。")

            avg_support_points = df_display["獲得支援point"].mean()
            avg_sg_total = df_display["期限あり/期限なしSG総額"].mean()
            avg_sg_gifters = df_display["期限あり/期限なしSGのギフティング人数"].mean()
            avg_gifters = df_display["ギフト人数"].mean()
            avg_commenters = df_display["コメント人数"].mean()

            hit_broadcasts = []
            for index, row in df_display.iterrows():
                hit_items = []
                if pd.notna(row['初ルーム来訪者数']) and row['合計視聴数'] > 0 and (row['初ルーム来訪者数'] / row['合計視聴数']) >= 0.10: hit_items.append('初見訪問者率')
                if pd.notna(row['初コメント人数']) and row['コメント人数'] > 0 and (row['初コメント人数'] / row['コメント人数']) >= 0.08: hit_items.append('初コメント率')
                if pd.notna(row['初ギフト人数']) and row['ギフト人数'] > 0 and (row['初ギフト人数'] / row['ギフト人数']) >= 0.10: hit_items.append('初ギフト率')
                if pd.notna(row['短時間滞在者数']) and row['視聴会員数'] > 0 and (row['短時間滞在者数'] / row['視聴会員数']) <= 0.20: hit_items.append('短時間滞在者率')
                if pd.notna(row['獲得支援point']) and row['獲得支援point'] >= avg_support_points * 2.5: hit_items.append('獲得支援point')
                if pd.notna(row['期限あり/期限なしSG総額']) and row['期限あり/期限なしSG総額'] >= avg_sg_total * 2.5: hit_items.append('SG総額')
                if pd.notna(row['期限あり/期限なしSGのギフティング人数']) and row['期限あり/期限なしSGのギフティング人数'] >= avg_sg_gifters * 2.0: hit_items.append('SGギフト人数')
                if pd.notna(row['ギフト人数']) and row['ギフト人数'] >= avg_gifters * 2.0: hit_items.append('ギフト人数')
                if pd.notna(row['コメント人数']) and row['コメント人数'] >= avg_commenters * 2.0: hit_items.append('コメント人数')

                if hit_items:
                    hit_broadcasts.append({
                        '配信日時': row['配信日時'],
                        'ヒット項目': ', '.join(hit_items),
                        'イベント名': row['イベント名']
                    })

            if hit_broadcasts:
                hit_df = pd.DataFrame(hit_broadcasts)
                st.dataframe(hit_df, hide_index=True, use_container_width=True)
                st.caption("※一部イベントのみイベント名に反映しています。")
            else:
                st.write("ヒットした配信はありませんでした。")

