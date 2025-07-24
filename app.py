import streamlit as st
st.set_page_config(layout="wide")
from streamlit_js_eval import streamlit_js_eval
import pandas as pd
from datetime import datetime, timedelta
import json
import os

DATA_PATH = "data.json"  # 資料檔案路徑
MAX_TEAM_SIZE = 6  # 每隊最大人數

# 讀取/初始化資料
def load_data():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip():
                # 檔案為空，自動建立預設資料
                data = {
                    "teams": [
                        {
                            "team_name": f"隊伍 {i+1}",
                            "boss_times": "",
                            "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(6)]
                        } for i in range(3)
                    ]
                }
            else:
                data = json.loads(content)
    else:
        data = {
            "teams": [
                {
                    "team_name": f"隊伍 {i+1}",
                    "boss_times": "",
                    "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(6)]
                } for i in range(3)
            ]
        }
    return data

def save_data(data):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 建立組隊資訊文字
def build_team_text(team):
            title = f"【{team['team_name']} 連7】"
            time = f"時間：{team['boss_times']}"
            members = []
            missing = []
            for i, member in enumerate(team["member"], 1):
                if member["name"]:
                    line = f"{i}. {member['level']} {member['job']}".strip()
                    line = f"{line} 乾表:{member['atk']}" if member['atk'] else line
                    members.append(line)
                else:
                    # 缺少成員
                    line = f"{member['job']}"
                    if member["atk"]:
                        line += f" ATK {member['atk']} ↑"
                    missing.append(line)
            member_text = "目前成員：\n" + "\n".join(members) if members else ""
            missing_text = "缺少成員：\n" + "\n".join(missing) + "\n私訊職業/表攻"  if missing else ""
            result = "\n".join([title, time, member_text, missing_text]).strip()         
            return result

# 初始化 session_state
if "data" not in st.session_state:
    st.session_state.data = load_data()

def sync_to_session():
    st.session_state.teams = st.session_state.data["teams"]

def sync_to_data():
    st.session_state.data["teams"] = st.session_state.teams
    save_data(st.session_state.data)

sync_to_session()


st.title("🛡️ 楓之谷公會 - 敲王組隊登記系統")
st.markdown(
""" 
📖 **使用說明**

1️⃣ 請於下方選擇欲加入的隊伍，並填寫個人資料。  
2️⃣ 【等級、表攻】僅供隊長複製訊息時參考，非必填。  
3️⃣ 若隊伍缺少成員，隊長可預填職業及表攻，按下「複製組隊資訊」即可產生徵人訊息。  
4️⃣ 請成員自行協調，依先登記者優先原則處理，請勿重複填寫同一隊伍。  
5️⃣ 隊長開設組隊時，請先確認【隊伍名稱】及【打王時間】，例如：「拉圖斯1隊 PM 9:00，日期待確認」。 


📮 如有任何問題或想新增功能，請聯絡管理員協助。
"""
)

def get_week_range():
    today = datetime.today()
    weekday = today.weekday()
    days_since_thu = (weekday - 3) % 7
    start = today - timedelta(days=days_since_thu)
    end = start + timedelta(days=6)
    week_str = f"{start.month}/{start.day}({['一','二','三','四','五','六','日'][start.weekday()]}) ~ {end.month}/{end.day}({['一','二','三','四','五','六','日'][end.weekday()]})"
    return week_str

st.markdown(f"### 本周時間：{get_week_range()}")

job_options = {
    "🛡": ["龍騎士", "十字軍", "騎士"],
    "🏹": ["狙擊手", "遊俠"],
    "🗡": ["暗殺者", "神偷"],
    "🏴‍☠️": ["格鬥家", "槍神"],
    "🧙‍♂️": ["魔導師（火毒）", "魔導師（冰雷）", "祭師"]
}
job_select_list = []
for emoji, jobs in job_options.items():
    job_select_list += [f"{emoji} {job}" for job in jobs]

# 顯示隊伍名單與本周打王時間 + 編輯/刪除成員功能
st.header("📋 當前隊伍名單")
for idx, team in enumerate(st.session_state.teams):
    # Expander 標題顯示隊伍名稱和打王時間
    expander_label = f"{team['team_name']}｜{team['boss_times'] if team['boss_times'] else '未設定打王時間'}"
    with st.expander(expander_label):
        # 編輯隊伍名稱
        team_name_input = st.text_input(
            f"隊伍名稱 {idx + 1}",
            value=team["team_name"],
            key=f"team_name_{idx}"
        )
        if team_name_input != team["team_name"]:
            team["team_name"] = team_name_input
            sync_to_data()
            st.success(f"隊伍 {idx + 1} 名稱已更新為：{team_name_input}！")

        # 編輯打王時間
        boss_time_input = st.text_input(
            f"{team['team_name']} - 打王時間（請自行輸入）",
            value=team["boss_times"],
            key=f"boss_time_text_{idx}"
        )
        if boss_time_input != team["boss_times"]:
            team["boss_times"] = boss_time_input
            sync_to_data()
            st.success(f"{team['team_name']} 的本周打王時間已更新為：{boss_time_input}！")

        # 初始化固定 6 人表格
        if not team["member"] or len(team["member"]) < 6:
            team["member"] = [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(6)]

        # 顯示表格
        col0, col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 2, 1])
        with col0:
            st.markdown("**#**")
        with col1:
            st.markdown("**名稱**")
        with col2:
            st.markdown("**職業**")
        with col3:
            st.markdown("**等級**")
        with col4:
            st.markdown("**表攻**")
        with col5:
            st.markdown("**操作**")

        for i, member in enumerate(team["member"]):
            col0, col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 2, 1])
            with col0:
                st.markdown(f"{i + 1}")
            with col1:
                member["name"] = st.text_input(f"名稱 {i + 1}", value=member["name"], key=f"name_{idx}_{i}")
            with col2:
                member["job"] = st.selectbox(f"職業 {i + 1}", [""] + job_select_list, index=job_select_list.index(member["job"]) + 1 if member["job"] in job_select_list else 0, key=f"job_{idx}_{i}")
            with col3:
                member["level"] = st.text_input(f"等級 {i + 1}", value=member["level"], key=f"level_{idx}_{i}")
            with col4:
                member["atk"] = st.text_input(f"表攻 {i + 1}", value=member["atk"], key=f"atk_{idx}_{i}")
            with col5:
                if st.button(f"清空", key=f"clear_{idx}_{i}"):
                    member["name"], member["job"], member["level"], member["atk"] = "", "", "", ""

        # 清空隊伍和刪除隊伍按鈕在同一行
        col_clear, col_delete = st.columns([1, 1])
        if "refresh" not in st.session_state:
            st.session_state.refresh = False

        with col_clear:
            if st.button(f"清空隊伍", key=f"clear_team_{idx}"):
                team["member"] = [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(6)]
                sync_to_data()
                st.success(f"{team['team_name']} 已清空！")
                st.session_state.refresh = True
        with col_delete:
            if st.button(f"刪除隊伍", key=f"delete_team_{idx}"):
                del st.session_state.teams[idx]
                sync_to_data()
                st.success(f"{team['team_name']} 已刪除！")
                st.session_state.refresh = True

        # 複製文字顯示/隱藏狀態（每隊獨立）
        if f"show_copy_{idx}" not in st.session_state:
            st.session_state[f"show_copy_{idx}"] = False

        def toggle_copy(idx=idx):
            st.session_state[f"show_copy_{idx}"] = not st.session_state[f"show_copy_{idx}"]

        st.button(
            "顯示/隱藏複製組隊資訊",
            key=f"toggle_copy_btn_{idx}",
            on_click=toggle_copy
        )
        
        if st.session_state[f"show_copy_{idx}"]:
            team_text = build_team_text(team)
            st.text_area("複製組隊資訊", value=team_text, key=f"copy_text_{idx}", height=300)
            if st.session_state.refresh:
                st.session_state.refresh = False
                streamlit_js_eval(js_expressions="parent.window.location.reload()")

        sync_to_data()

# 增加隊伍按鈕（新增時可輸入隊伍名稱）
with st.form("add_team_form", clear_on_submit=True):
    new_team_name = st.text_input("新隊伍名稱(盡量不要相同名稱)", value=f"隊伍 {len(st.session_state.teams)+1}")
    add_team_submit = st.form_submit_button("➕ 增加隊伍")
    if add_team_submit:
        st.session_state.teams.append({
            "team_name": new_team_name,
            "boss_times": "",
            "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(6)]
        })
        sync_to_data()
        st.success(f"已增加隊伍：{new_team_name}！")
        streamlit_js_eval(js_expressions="parent.window.location.reload()")
