import streamlit as st
import pandas as pd
import numpy as np
import io
import requests

# ページ設定
st.set_page_config(
    page_title="SHOWROOMライバーKPI分析ツール",
    page_icon="📊",
    layout="wide"
)

# ヘッダー
st.title("SHOWROOMライバーKPI分析ツール")
st.markdown("ライブ配信データから、フォロワーやポイント獲得の傾向を分析し、今後の戦略を検討しましょう。")

# メンバーID入力
member_id = st.text_input(
    "分析したいライバーのメンバーIDを入力してください",
    "343547_natsume" # 例としてデフォルト値を設定
)

# データの読み込みと前処理関数
def load_and_preprocess_data(member_id):
    """
    指定されたメンバーIDのCSVをURLから読み込み、前処理を行う
    """
    if not member_id:
        st.error("メンバーIDを入力してください。")
        return None

    # URLを生成（2025年8月を固定）
    url = f"https://mksoul-pro.com/showroom/csv/2025-08_all_{member_id}.csv"
    
    try:
        # requestsを使ってURLからCSVデータを取得
        response = requests.get(url)
        response.raise_for_status()  # HTTPエラーをチェック
        
        # バイナリデータをStringIOで読み込める形に変換
        csv_data = io.StringIO(response.text)
        
        # CSVを読み込む
        # encodingを'cp932'に設定することで、日本語の文字化けを防止
        # ヘッダーとデータ行の列数が一致しない問題を解決するため、最後の列を削除
        df = pd.read_csv(csv_data, encoding='cp932')
        
        # 列名から前後の空白と引用符を削除
        df.columns = df.columns.str.strip().str.replace('"', '')
        
        # ヘッダーとデータ行の列数が一致しない問題を解決するため、最後の列を削除
        df = df.iloc[:, :-1]

        # データ型変換とクリーンアップ
        for col in [
            "合計視聴数", "視聴会員数", "フォロワー数", "獲得支援point", "コメント数",
            "ギフト数", "期限あり/期限なしSG総額", "コメント人数", "初コメント人数",
            "ギフト人数", "初ギフト人数", "フォロワー増減数"
        ]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(",", "").replace("-", "0").astype(float)
        
        # "配信日時"列をdatetime型に変換
        if "配信日時" in df.columns:
            df["配信日時"] = pd.to_datetime(df["配信日時"])
        else:
            raise KeyError("'配信日時' 列が見つかりません。")

        return df

    except requests.exceptions.RequestException as e:
        st.error(f"データの読み込み中にエラーが発生しました。メンバーIDが正しいか、URLにアクセスできるか確認してください。エラー: {e}")
        return None
    except Exception as e:
        st.error(f"CSVファイルの処理中に予期せぬエラーが発生しました。詳細: {e}")
        return None

# 分析実行ボタン
if st.button("分析を実行"):
    df = load_and_preprocess_data(member_id)
    if df is not None and not df.empty:
        st.success("データの読み込みと前処理が完了しました！")
        
        # 分析と可視化
        st.subheader("📈 主要KPIの推移")
        st.line_chart(df.set_index("配信日時")[["獲得支援point", "フォロワー増減数", "コメント数"]])
        
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
        total_point_increase = int(df["フォロワー増減数"].sum()) # フォロワー増減の合計
        
        st.markdown(f"**合計獲得支援ポイント:** {total_support_points:,} pt")
        st.markdown(f"**フォロワー純増数:** {total_point_increase:,} 人")
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

    elif df is not None and df.empty:
        st.warning("指定されたメンバーIDのデータが見つかりませんでした。")