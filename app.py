import streamlit as st
import pandas as pd
import numpy as np
import io
import requests
from datetime import date, timedelta
import plotly.express as px

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
    "分析したいライバーの**アカウントID**を入力してください",
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

    # 日付範囲内のすべての月を特定
    all_dfs = []
    current_date = start_date
    while current_date <= end_date:
        year = current_date.year
        month = current_date.month
        
        url = f"https://mksoul-pro.com/showroom/csv/{year:04d}-{month:02d}_all_all.csv"
        
        try:
            # requestsを使ってURLからCSVデータを取得
            response = requests.get(url)
            response.raise_for_status()  # HTTPエラーをチェック
            
            # BOM付きUTF-8に対応するため、decode('utf-8-sig')を使用
            csv_text = response.content.decode('utf-8-sig')
            
            # 各行を処理
            lines = csv_text.strip().split('\n')
            header_line = lines[0]
            data_lines = lines[1:]
            
            # ヘッダーとデータ行の列数を一致させるため、余分な列を削除
            cleaned_data_lines = [','.join(line.split(',')[:-1]) for line in data_lines]
            cleaned_csv_text = header_line + '\n' + '\n'.join(cleaned_data_lines)
            
            # StringIOを使ってpandasに渡す
            csv_data = io.StringIO(cleaned_csv_text)
            df = pd.read_csv(csv_data)
            
            # 列名から前後の空白と引用符を削除
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            all_dfs.append(df)
            
        except requests.exceptions.RequestException as e:
            st.warning(f"{year}年{month}月のデータが見つかりませんでした。スキップします。")
        except Exception as e:
            st.error(f"CSVファイルの処理中に予期せぬエラーが発生しました。詳細: {e}")
            return None
            
        # 次の月に移動
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)

    if not all_dfs:
        st.error(f"選択された期間のデータが一つも見つかりませんでした。")
        return None

    # すべてのデータフレームを結合
    combined_df = pd.concat(all_dfs, ignore_index=True)

    # "配信日時"列をdatetime型に変換
    if "配信日時" not in combined_df.columns:
        raise KeyError("CSVファイルに '配信日時' 列が見つかりませんでした。")
    combined_df["配信日時"] = pd.to_datetime(combined_df["配信日時"])

    # ユーザーが入力したアカウントIDでデータをフィルタリング
    filtered_df = combined_df[combined_df["アカウントID"] == account_id].copy()
    
    # 日付範囲でさらにフィルタリング
    filtered_df = filtered_df[
        (filtered_df["配信日時"].dt.date >= start_date) & 
        (filtered_df["配信日時"].dt.date <= end_date)
    ].copy()

    if filtered_df.empty:
        st.warning(f"指定されたアカウントID（{account_id}）のデータが選択された期間に見つかりませんでした。")
        return None

    # データ型変換とクリーンアップ
    for col in [
        "合計視聴数", "視聴会員数", "フォロワー数", "獲得支援point", "コメント数",
        "ギフト数", "期限あり/期限なしSG総額", "コメント人数", "初コメント人数",
        "ギフト人数", "初ギフト人数", "フォロワー増減数", "初ルーム来訪者数"
    ]:
        if col in filtered_df.columns:
            filtered_df[col] = filtered_df[col].astype(str).str.replace(",", "").replace("-", "0").astype(float)

    return filtered_df

# 分析実行ボタン
if st.button("分析を実行"):
    if len(selected_date_range) == 2:
        start_date = selected_date_range[0]
        end_date = selected_date_range[1]
        df = load_and_preprocess_data(account_id, start_date, end_date)
        if df is not None and not df.empty:
            st.success("データの読み込みと前処理が完了しました！")
            
            # --- 修正点: すべての計算・表示の前に、データを最新順に並び替え ---
            df = df.sort_values(by="配信日時", ascending=True).copy()
            
            # 分析と可視化
            st.subheader("📈 主要KPIの推移")
            # Plotlyを使用してグラフを作成（時間表示に対応）
            fig = px.line(
                df,
                x="配信日時",
                y=["獲得支援point", "フォロワー増減数", "コメント数"],
                labels={
                    "value": "値",
                    "variable": "KPI"
                },
                title="KPIの推移（配信時間別）"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # 詳細データテーブルの表示
            st.subheader("📝 配信ごとの詳細データ")
            # 配信日時で降順に並び替え（表示用）
            df_display = df.sort_values(by="配信日時", ascending=False)
            st.dataframe(df_display, hide_index=True)

            st.subheader("🎯 初見/リピーター分析")
            col1, col2, col3 = st.columns(3)
            
            total_visitors = df["視聴会員数"].sum()
            first_time_visitors = df["初ルーム来訪者数"].sum()
            
            # 視聴会員数ベースの初見率
            with col1:
                st.metric(
                    label="初見訪問者率",
                    value=f"{first_time_visitors / total_visitors * 100:.1f}%" if total_visitors > 0 else "0%",
                    help="合計視聴会員数に対する初ルーム来訪者数の割合です。新規ファン獲得の効率を示します。"
                )
                
            # コメント人数ベースの初見率
            with col2:
                total_commenters = df["コメント人数"].sum()
                first_time_commenters = df["初コメント人数"].sum()
                st.metric(
                    label="初コメント率",
                    value=f"{first_time_commenters / total_commenters * 100:.1f}%" if total_commenters > 0 else "0%",
                    help="合計コメント人数に対する初コメント人数の割合です。新規リスナーの参加度合いを示します。"
                )

            # ギフト人数ベースの初見率
            with col3:
                total_gifters = df["ギフト人数"].sum()
                first_time_gifters = df["初ギフト人数"].sum()
                st.metric(
                    label="初ギフト率",
                    value=f"{first_time_gifters / total_gifters * 100:.1f}%" if total_gifters > 0 else "0%",
                    help="合計ギフト人数に対する初ギフト人数の割合です。新規ファンの課金状況を示します。"
                )

            # 全体サマリー
            st.subheader("📝 全体サマリー")
            total_support_points = int(df["獲得支援point"].sum())
            total_followers = int(df["フォロワー数"].iloc[-1]) # 最新のフォロワー数
            
            # --- 修正点: フォロワー純増数の計算方法を変更 ---
            initial_followers = int(df["フォロワー数"].iloc[0])
            total_follower_increase = total_followers - initial_followers
            
            st.markdown(f"**合計獲得支援ポイント:** {total_support_points:,} pt")
            st.markdown(f"**フォロワー純増数:** {total_follower_increase:,} 人")
            st.markdown(f"**最終フォロワー数:** {total_followers:,} 人")
            
            # 戦略的な示唆
            st.subheader("💡 今後の戦略的示唆")
            avg_support_per_viewer = (df["獲得支援point"] / df["視聴会員数"]).mean()
            avg_comments_per_viewer = (df["コメント人数"] / df["視聴会員数"]).mean()
            
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