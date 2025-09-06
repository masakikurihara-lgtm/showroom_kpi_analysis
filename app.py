import streamlit as st
import pandas as pd
import numpy as np
import io
import requests
from datetime import date, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import streamlit.components.v1 as components

# ページ設定
st.set_page_config(
    page_title="SHOWROOMライバーKPI分析ツール",
    page_icon="📊",
    layout="wide"
)

# ヘッダー
st.title("SHOWROOMライバーKPI分析ツール")
st.markdown("ライブ配信データから、フォロワーやポイント獲得の傾向を分析し、今後の戦略を検討しましょう。")

# 入力フィールド
account_id = st.text_input(
    "分析したいライバーの**アカウントID**を入力してください（全員分は**mksp**）",
    ""
)

# 日付範囲の選択ウィジェット
st.subheader("🗓️ 分析期間を選択")
today = date.today()
default_start_date = today - timedelta(days=30)
default_end_date = today
selected_date_range = st.date_input(
    "日付範囲",
    (default_start_date, default_end_date),
    max_value=today
)

# データの読み込みと前処理関数
def load_and_preprocess_data(account_id, start_date, end_date):
    """
    指定された日付範囲の全員分のCSVをURLから読み込み、指定されたアカウントIDのデータのみを抽出して前処理を行う
    """
    if not account_id:
        st.error("アカウントIDを入力してください。")
        return None
    
    if start_date > end_date:
        st.error("開始日は終了日より前の日付を選択してください。")
        return None

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
            return None
            
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)

    if not all_dfs:
        st.error(f"選択された期間のデータが一つも見つかりませんでした。")
        return None

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
        return None

    for col in [
        "合計視聴数", "視聴会員数", "フォロワー数", "獲得支援point", "コメント数",
        "ギフト数", "期限あり/期限なしSG総額", "コメント人数", "初コメント人数",
        "ギフト人数", "初ギフト人数", "フォロワー増減数", "初ルーム来訪者数", "配信時間(分)"
    ]:
        if col in filtered_df.columns:
            filtered_df[col] = filtered_df[col].astype(str).str.replace(",", "").replace("-", "0").astype(float)

    return filtered_df

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

if st.button("分析を実行"):
    if len(selected_date_range) == 2:
        start_date = selected_date_range[0]
        end_date = selected_date_range[1]
        df = load_and_preprocess_data(account_id, start_date, end_date)
        if df is not None and not df.empty:
            st.success("データの読み込みと前処理が完了しました！")
            
            if account_id == "mksp":
                st.subheader("💡 全ライバーの集計データ")
                st.info("このビューでは、個人のフォロワー関連データは表示されません。")
                
                total_support_points = int(df["獲得支援point"].sum())
                total_viewers = int(df["合計視聴数"].sum())
                total_comments = int(df["コメント数"].sum())
                
                st.markdown(f"**合計獲得支援ポイント:** {total_support_points:,} pt")
                st.markdown(f"**合計視聴数:** {total_viewers:,} 人")
                st.markdown(f"**合計コメント数:** {total_comments:,} 件")

                st.subheader("📝 全ライバーの配信詳細データ")
                df_display = df.sort_values(by="配信日時", ascending=False)
                st.dataframe(df_display, hide_index=True)

            else:
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
                
                st.subheader("📊 時間帯別パフォーマンス分析")
                
                df['時間帯'] = df['配信日時'].dt.hour.apply(categorize_time_of_day_with_range)
                
                time_of_day_kpis = df.groupby('時間帯').agg({
                    '獲得支援point': 'mean',
                    '合計視聴数': 'mean',
                    'コメント数': 'mean'
                }).reset_index()

                time_of_day_order = [
                    "深夜 (0-3時)", "早朝 (3-6時)", "朝 (6-9時)", "午前 (9-12時)", 
                    "昼 (12-15時)", "午後 (15-18時)", "夜前半 (18-21時)", 
                    "夜ピーク (21-22時)", "夜後半 (22-24時)"
                ]
                time_of_day_kpis['時間帯'] = pd.Categorical(time_of_day_kpis['時間帯'], categories=time_of_day_order, ordered=True)
                time_of_day_kpis = time_of_day_kpis.sort_values('時間帯')

                # PCとスマホの切り替えをplotlyの設定で対応
                # スマホでは縦に並べる
                fig_mobile = make_subplots(
                    rows=3, cols=1,
                    subplot_titles=("獲得支援point", "合計視聴数", "コメント数"),
                )
                fig_mobile.add_trace(go.Bar(x=time_of_day_kpis['時間帯'], y=time_of_day_kpis['獲得支援point'], name='獲得支援point'), row=1, col=1)
                fig_mobile.add_trace(go.Bar(x=time_of_day_kpis['時間帯'], y=time_of_day_kpis['合計視聴数'], name='合計視聴数'), row=2, col=1)
                fig_mobile.add_trace(go.Bar(x=time_of_day_kpis['時間帯'], y=time_of_day_kpis['コメント数'], name='コメント数'), row=3, col=1)
                fig_mobile.update_layout(
                    title_text="時間帯別KPI平均値",
                    showlegend=False,
                    height=800,
                    margin=dict(t=50, b=100, l=40, r=40),
                    font=dict(size=10)
                )
                fig_mobile.update_yaxes(title_text="獲得支援point", row=1, col=1)
                fig_mobile.update_yaxes(title_text="合計視聴数", row=2, col=1)
                fig_mobile.update_yaxes(title_text="コメント数", row=3, col=1)

                # PCでは横に並べる
                fig_pc = make_subplots(
                    rows=1, cols=3,
                    subplot_titles=("獲得支援point", "合計視聴数", "コメント数"),
                )
                fig_pc.add_trace(go.Bar(x=time_of_day_kpis['時間帯'], y=time_of_day_kpis['獲得支援point'], name='獲得支援point'), row=1, col=1)
                fig_pc.add_trace(go.Bar(x=time_of_day_kpis['時間帯'], y=time_of_day_kpis['合計視聴数'], name='合計視聴数'), row=1, col=2)
                fig_pc.add_trace(go.Bar(x=time_of_day_kpis['時間帯'], y=time_of_day_kpis['コメント数'], name='コメント数'), row=1, col=3)
                fig_pc.update_layout(
                    title_text="時間帯別KPI平均値",
                    showlegend=False,
                    height=400,
                    margin=dict(t=50, b=100, l=40, r=40),
                    font=dict(size=12)
                )
                fig_pc.update_yaxes(title_text="獲得支援point", row=1, col=1)
                fig_pc.update_yaxes(title_text="合計視聴数", row=1, col=2)
                fig_pc.update_yaxes(title_text="コメント数", row=1, col=3)

                # StreamlitのCSSマジックでPC/スマホを判別し表示
                st.markdown("""
                    <style>
                    /* PC用のスタイル（768px以上） */
                    @media (min-width: 768px) {
                        #mobile-graphs { display: none; }
                    }
                    /* スマホ用のスタイル（768px未満） */
                    @media (max-width: 767px) {
                        #pc-graphs { display: none; }
                    }
                    </style>
                """, unsafe_allow_html=True)

                st.markdown("<div id='pc-graphs'>", unsafe_allow_html=True)
                st.plotly_chart(fig_pc, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("<div id='mobile-graphs'>", unsafe_allow_html=True)
                st.plotly_chart(fig_mobile, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
                
                st.markdown("<br><br>", unsafe_allow_html=True)
                
                st.subheader("📝 配信ごとの詳細データ")
                df_display = df_sorted_asc.sort_values(by="配信日時", ascending=False)
                st.dataframe(df_display, hide_index=True)

                st.subheader("🎯 初見/リピーター分析")
                col1, col2, col3 = st.columns(3)
                
                total_visitors = df_sorted_asc["視聴会員数"].sum()
                first_time_visitors = df_sorted_asc["初ルーム来訪者数"].sum()
                
                with col1:
                    st.metric(
                        label="初見訪問者率",
                        value=f"{first_time_visitors / total_visitors * 100:.1f}%" if total_visitors > 0 else "0%",
                        help="合計視聴会員数に対する初ルーム来訪者数の割合です。新規ファン獲得の効率を示します。"
                    )
                    
                with col2:
                    total_commenters = df_sorted_asc["コメント人数"].sum()
                    first_time_commenters = df_sorted_asc["初コメント人数"].sum()
                    st.metric(
                        label="初コメント率",
                        value=f"{first_time_commenters / total_commenters * 100:.1f}%" if total_commenters > 0 else "0%",
                        help="合計コメント人数に対する初コメント人数の割合です。新規リスナーの参加度合いを示します。"
                    )

                with col3:
                    total_gifters = df_sorted_asc["ギフト人数"].sum()
                    first_time_gifters = df_sorted_asc["初ギフト人数"].sum()
                    st.metric(
                        label="初ギフト率",
                        value=f"{first_time_gifters / total_gifters * 100:.1f}%" if total_gifters > 0 else "0%",
                        help="合計ギフト人数に対する初ギフト人数の割合です。新規ファンの課金状況を示します。"
                    )

                st.subheader("📝 全体サマリー")
                total_support_points = int(df_sorted_asc["獲得支援point"].sum())
                if not df_sorted_asc.empty:
                    total_followers = int(df_sorted_asc["フォロワー数"].iloc[-1])
                    initial_followers = int(df_sorted_asc["フォロワー数"].iloc[0])
                    total_follower_increase = total_followers - initial_followers
                    st.markdown(f"**フォロワー純増数:** {total_follower_increase:,} 人")
                    st.markdown(f"**最終フォロワー数:** {total_followers:,} 人")
                
                st.markdown(f"**合計獲得支援ポイント:** {total_support_points:,} pt")

                
                st.subheader("💡 今後の戦略的示唆")
                avg_support_per_viewer = (df_sorted_asc["獲得支援point"] / df_sorted_asc["視聴会員数"]).mean()
                avg_comments_per_viewer = (df_sorted_asc["コメント人数"] / df_sorted_asc["視聴会員数"]).mean()
                
                if avg_support_per_viewer > 50:
                    st.markdown("👉 視聴会員数あたりの獲得支援ポイントが高い傾向にあります。熱心なファン層が定着しているようです。")
                else:
                    st.markdown("👉 視聴会員数あたりの獲得支援ポイントがやや低い傾向にあります。新規リスナーやライト層へのアプローチを強化し、課金を促す工夫を検討しましょう。")

                if avg_comments_per_viewer > 0.1:
                    st.markdown("👉 視聴会員数に対するコメント人数が多いです。積極的にコミュニケーションを取れており、参加型の配信が成功しています。")
                else:
                    st.markdown("👉 視聴会員数に対するコメント人数が少ないです。リスナーがコメントしやすいような質問を投げかけたり、イベントを活用してコメントを促す工夫を検討しましょう。")

        else:
            st.warning(f"指定されたアカウントID（{account_id}）のデータが{start_date}～{end_date}の期間に見つかりませんでした。")