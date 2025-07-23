import streamlit as st
st.set_page_config(layout="wide")
from streamlit_js_eval import streamlit_js_eval
import pandas as pd
from datetime import datetime, timedelta
import json
import os

DATA_PATH = "data.json"

# 讀取/初始化資料
def load_data():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {
            "teams": [[] for _ in range(3)],
            "boss_times": [None for _ in range(3)],
            "num_teams": 3
        }
    return data

def save_data(data):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 初始化 session_state
if "data" not in st.session_state:
    st.session_state.data = load_data()

def sync_to_session():
    st.session_state.teams = st.session_state.data["teams"]
    st.session_state.boss_times = st.session_state.data["boss_times"]
    st.session_state.num_teams = st.session_state.data["num_teams"]

def sync_to_data():
    st.session_state.data["teams"] = st.session_state.teams
    st.session_state.data["boss_times"] = st.session_state.boss_times
    st.session_state.data["num_teams"] = st.session_state.num_teams
    save_data(st.session_state.data)

sync_to_session()

# 設定管理員密碼
ADMIN_PASSWORD = "123456"

MAX_TEAM_SIZE = 6

st.title("🛡️ 楓之谷公會 - 敲王組隊登記系統")
st.markdown("請填寫下方資料並選擇要加入的隊伍，每隊上限 6 人，可動態新增隊伍。")

# 1. 顯示本周時間區間
def get_week_range():
    today = datetime.today()
    weekday = today.weekday()  # 0=Monday, 3=Thursday
    # 以禮拜四為一周的開始
    days_since_thu = (weekday - 3) % 7
    start = today - timedelta(days=days_since_thu)
    end = start + timedelta(days=6)
    week_str = f"{start.month}/{start.day}({['一','二','三','四','五','六','日'][start.weekday()]}) ~ {end.month}/{end.day}({['一','二','三','四','五','六','日'][end.weekday()]})"
    return week_str

st.markdown(f"### 本周時間：{get_week_range()}")

# 4. 職業選單
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
for idx in range(st.session_state.num_teams):
    with st.expander(f"隊伍 {idx + 1}"):
        team = st.session_state.teams[idx]
        boss_time = st.session_state.boss_times[idx]

        # 移除原本的日期與時間選擇，改為文字輸入
        boss_time_input = st.text_input(
            f"隊伍 {idx + 1} - 打王時間（請自行輸入）",
            value=boss_time if boss_time else "",
            key=f"boss_time_text_{idx}"
        )
        if boss_time_input != (boss_time if boss_time else ""):
            st.session_state.boss_times[idx] = boss_time_input
            sync_to_data()
            st.success(f"隊伍 {idx + 1} 的本周打王時間已更新為：{boss_time_input}！")

        # 初始化固定 4x6 表格
        if not team or len(team) < 6:
            team = [{"name": "", "job": "", "level": "", "score": ""} for _ in range(6)]
            st.session_state.teams[idx] = team

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
            st.markdown("**表功**")
        with col5:
            st.markdown("**操作**")

        for i, member in enumerate(team):
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
                member["score"] = st.text_input(f"表功 {i + 1}", value=member["score"], key=f"score_{idx}_{i}")
            with col5:
                if st.button(f"清空", key=f"clear_{idx}_{i}"):
                    member["name"], member["job"], member["level"], member["score"] = "", "", "", ""

        # 清空隊伍和刪除隊伍按鈕在同一行
        col_clear, col_delete = st.columns([1, 1])
        if "refresh" not in st.session_state:
            st.session_state.refresh = False

        with col_clear:
            if st.button(f"清空隊伍 {idx + 1}", key=f"clear_team_{idx}"):
                st.session_state.teams[idx] = [{"name": "", "job": "", "level": "", "score": ""} for _ in range(6)]
                sync_to_data()
                st.success(f"隊伍 {idx + 1} 已清空！")
                st.session_state.refresh = True  # Trigger refresh
        with col_delete:
            if st.button(f"刪除隊伍 {idx + 1}", key=f"delete_team_{idx}"):
                del st.session_state.teams[idx]
                del st.session_state.boss_times[idx]
                st.session_state.num_teams -= 1
                sync_to_data()
                st.success(f"隊伍 {idx + 1} 已刪除！")
                st.session_state.refresh = True  # Trigger refresh

        # Check refresh flag and reset it
        if st.session_state.refresh:
            st.session_state.refresh = False
            streamlit_js_eval(js_expressions="parent.window.location.reload()")  # Refresh indirectly

        sync_to_data()

# 管理員功能
with st.expander("🧹 管理員功能"):
    admin_pwd = st.text_input("請輸入管理員密碼", type="password")
    reset_json_btn = st.button("清空所有資料")
    if reset_json_btn:
        if admin_pwd == ADMIN_PASSWORD:
            st.session_state.data = {
                "teams": [[] for _ in range(3)],
                "boss_times": [None for _ in range(3)],
                "num_teams": 3
            }
            sync_to_session()
            save_data(st.session_state.data)
            st.success("所有資料已清空！")
            streamlit_js_eval(js_expressions="parent.window.location.reload()")  # 刷新頁面
        else:
            st.error("密碼錯誤，無法清空資料！")

# 增加隊伍按鈕
if st.button("➕ 增加隊伍"):
    st.session_state.teams.append([{"name": "", "job": "", "level": "", "score": ""} for _ in range(6)])
    st.session_state.boss_times.append(None)
    st.session_state.num_teams += 1
    sync_to_data()
    st.success(f"已增加隊伍 {st.session_state.num_teams}！")
    streamlit_js_eval(js_expressions="parent.window.location.reload()")  # 刷新頁面
