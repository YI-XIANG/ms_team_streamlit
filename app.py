import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests

st.set_page_config(layout="wide", page_title="楓之谷組隊系統", page_icon="🍁")

# --- 常數與設定 ---
MAX_TEAM_SIZE = 6
JOB_OPTIONS = {
    "🛡 劍士": ["龍騎士", "十字軍", "騎士"],
    "🏹 弓箭手": ["狙擊手", "遊俠"],
    "🗡 盜賊": ["暗殺者", "神偷"],
    "🏴‍☠️ 海盜": ["格鬥家", "槍神"],
    "🧙‍♂️ 法師": ["火毒", "冰雷", "祭師"]
}
JOB_SELECT_LIST = [job for sublist in JOB_OPTIONS.values() for job in sublist]


# --- 資料處理函式 ---
def load_data():
    firebase_url = st.secrets["firebase"]["url"] # 應指向根目錄 .json
    try:
        # 使用 auth 參數來讀取，確保規則一致性
        response = requests.get(firebase_url)
        if response.status_code == 200:
            data = response.json()
            if data is None: # Firebase 中無資料時返回 null
                return {"teams": [], "members": {}}
            # 確保 teams 和 members 欄位存在
            data.setdefault("teams", [])
            data.setdefault("members", {})
            return data
        else:
             st.error(f"❌ 無法從 Firebase 載入資料，狀態碼：{response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"❌ 載入資料時發生例外：{e}")

    # 返回一個安全的預設結構
    return {"teams": [], "members": {}}


def save_data(data):
    firebase_url = st.secrets["firebase"]["url"]
    try:
        response = requests.put(firebase_url, json=data)
        if response.status_code != 200:
            st.warning(f"⚠️ 儲存失敗，HTTP {response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"❌ 儲存資料時發生例外：{e}")


def build_team_text(team):
    title = f"【{team['team_name']} 徵人】"
    time = f"時間：{team['boss_times']}"
    members, missing = [], []
    current_members = [m for m in team.get("member", []) if m.get("name")]

    for i, member in enumerate(current_members, 1):
        line = f"{i}. {member.get('level','')} {member.get('job','')}".strip()
        if member.get("atk"):
            line += f" (乾表: {member.get('atk')})"
        members.append(line)
        
    for member_slot in team.get("member", []):
        if not member_slot.get("name"):
            line = f"{member_slot.get('job', '')}"
            if member_slot.get("atk"):
                line += f" (乾表: {member_slot.get('atk')} ↑)"
            if line.strip():
                missing.append(line)
                
    member_text = "✅ 目前成員：\n" + "\n".join(members) if members else ""
    missing_text = "📋 缺少成員：\n" + "\n".join(missing) if missing else "缺少打手，歡迎私訊！"
    result = "\n\n".join(filter(None, [title, time, member_text, missing_text])).strip()
    return result


def get_week_range():
    today = datetime.today()
    days_since_thu = (today.weekday() - 3) % 7
    start_of_week = today - timedelta(days=days_since_thu)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%m/%d')} ~ {end_of_week.strftime('%m/%d')}"



# --- 初始化 Session State ---
if "data" not in st.session_state:
    st.session_state.data = load_data()

def sync_data_and_save():
    save_data(st.session_state.data)
    
st.title("🍁 Monarchs公會組隊系統 🍁")
# --- UI 介面 ---
with st.expander("📝 系統介紹"):
    st.markdown(f"""
    ### 本周區間：{get_week_range()}
    1.  **【註冊角色】**
        在本頁下方的 **👤 公會成員名冊** 區塊，填寫你的遊戲 ID、職業、等級和表攻，並【儲存】。
    
    2.  **【加入隊伍】**
        找到想加入的隊伍，點開後在「名稱」欄位從下拉選單中找到並選擇你的名字。
    
    3.  **【儲存隊伍】**
        確認隊伍名單後，點擊該隊伍下方的 **【💾 儲存變更】** 按鈕，就完成組隊囉！
    
    > ### ⚠️ **拉圖斯（鐘王）隊伍建議**
    > *   **所有職業**：建議等級 **105** 以上。
    > *   **法系職業**：建議總魔攻（AP） **650** 以上。
    >
    > 💡 **小提示**：如果你的等級或裝備有變動，記得回到 **👤 公會成員名冊** 更新你的資料喔！
    
    <span style="color:red;">※ 注意事項：每位成員每週以報名 1 組為原則；若需報名 2 組，請自行購買「突襲額外獎勵票券」。請勿報名後缺席，以免造成隊友困擾，感謝配合。</span>
    """, unsafe_allow_html=True)


# --- 【新功能】公會成員名冊 ---
st.header("👤 公會成員名冊")
with st.expander("點此註冊或更新你的個人資料"):
    all_members = st.session_state.data.get("members", {})
    
    # 讓使用者可以選擇現有角色更新，或輸入新角色註冊
    member_list_for_select = [""] + list(all_members.keys())
    selected_member_name = st.selectbox("選擇你的角色 (或留空以註冊新角色)", options=member_list_for_select, key="member_select")
    
    # 根據選擇帶入資料
    default_info = all_members.get(selected_member_name, {"job": "", "level": "", "atk": ""})
    
    with st.form("member_form", clear_on_submit=False):
        st.write("**請填寫你的角色資訊：**")
        name_col, job_col = st.columns(2)
        level_col, atk_col = st.columns(2)
        
        with name_col:
            # 如果是選擇現有角色，名稱欄位鎖定，避免改名產生新角色
            if selected_member_name:
                name = st.text_input("遊戲ID (名稱)", value=selected_member_name, disabled=True)
            else:
                name = st.text_input("遊戲ID (名稱)", placeholder="請輸入你的完整遊戲名稱")
        with job_col:
            job = st.selectbox("職業", options=JOB_SELECT_LIST, index=JOB_SELECT_LIST.index(default_info.get("job", "")) if default_info.get("job") in JOB_SELECT_LIST else 0)
        with level_col:
            level = st.text_input("等級", value=default_info.get("level", ""))
        with atk_col:
            atk = st.text_input("表攻 (乾表)", value=default_info.get("atk", ""))
        
        submit_col, delete_col = st.columns([4,1])
        with submit_col:
            submitted = st.form_submit_button("💾 儲存角色資料")
            if submitted:
                final_name = selected_member_name or name
                if not final_name:
                    st.warning("請務必填寫遊戲ID！")
                else:
                    st.session_state.data["members"][final_name] = {"job": job, "level": level, "atk": atk}
                    sync_data_and_save()
                    st.success(f"角色 '{final_name}' 的資料已儲存！")
                    st.rerun() # 重跑以更新下拉選單
        with delete_col:
             if selected_member_name: # 只有選擇了現有角色才能刪除
                if st.form_submit_button("🗑️ 刪除此角色"):
                    del st.session_state.data["members"][selected_member_name]
                    sync_data_and_save()
                    st.success(f"角色 '{selected_member_name}' 已從名冊中刪除！")
                    st.rerun()

st.header("📋 當前隊伍名單")

teams = st.session_state.data.get("teams", [])
all_members = st.session_state.data.get("members", {})
# 製作一個包含空選項和所有已註冊成員的列表，供組隊表格使用
member_names_for_team_select = [""] + list(all_members.keys())

for idx, team in enumerate(teams):
    if "member" not in team or len(team["member"]) < MAX_TEAM_SIZE:
        team["member"] = [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)]
    
    expander_label = f"🍁 **{team['team_name']}**｜📅 {team.get('boss_times', '時間未定')}"
    
    with st.expander(expander_label):
        member_count = sum(1 for m in team["member"] if m.get("name"))
        c1, c2 = st.columns([3, 1])
        with c1:
            st.progress(member_count / MAX_TEAM_SIZE, text=f"👥 人數: {member_count} / {MAX_TEAM_SIZE}")
        with c2:
            st.info(f"✨ 尚缺 {MAX_TEAM_SIZE - member_count} 人" if member_count < MAX_TEAM_SIZE else "🎉 人數已滿")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            new_team_name = st.text_input("隊伍名稱", value=team["team_name"], key=f"name_{idx}")
        with col2:
            new_boss_times = st.text_input("打王時間", value=team["boss_times"], key=f"time_{idx}")
            
        st.write("**編輯隊伍成員 (請從名稱欄位選擇成員)：**")
        
        # --- 【核心改造】動態更新的組隊表格 ---
        # 將隊伍成員轉換為 DataFrame 以便使用 st.data_editor
        df = pd.DataFrame(team["member"])
        for col in ['name', 'job', 'level', 'atk']:
            if col not in df.columns:
                df[col] = ""
        df = df[['name', 'job', 'level', 'atk']]
        
        # 使用 data_editor 顯示
        edited_df = st.data_editor(
            df,
            key=f"editor_{idx}",
            num_rows="fixed",
            use_container_width=True,
            column_config={
                "_index": None,
                "name": st.column_config.SelectboxColumn("名稱", options=member_names_for_team_select, required=False, help="從名冊選擇成員"),
                "job": st.column_config.TextColumn("職業", disabled=True), # 職業、等級、表攻變為不可手動編輯
                "level": st.column_config.TextColumn("等級", disabled=True),
                "atk": st.column_config.TextColumn("表攻", disabled=True),
            },
            column_order=("name", "job", "level", "atk")
        )
        
        st.markdown("---")
        
        btn_cols = st.columns([1.5, 1, 1, 1.5])
        
        with btn_cols[0]:
            if st.button(f"💾 儲存變更", key=f"save_{idx}", type="primary"):
                # 【核心邏輯】儲存時，根據選擇的名稱，從 `all_members` 重新抓取最新資料填入
                updated_members = []
                for _, row in edited_df.iterrows():
                    member_name = row["name"]
                    if member_name and member_name in all_members:
                        # 從名冊拉取最新資料
                        member_data = all_members[member_name]
                        updated_members.append({
                            "name": member_name,
                            "job": member_data.get("job", ""),
                            "level": member_data.get("level", ""),
                            "atk": member_data.get("atk", "")
                        })
                    else:
                        # 如果是空格或無效名稱，則保留空位
                        updated_members.append({"name": "", "job": "", "level": "", "atk": ""})

                st.session_state.data["teams"][idx]["team_name"] = new_team_name
                st.session_state.data["teams"][idx]["boss_times"] = new_boss_times
                st.session_state.data["teams"][idx]["member"] = updated_members
                sync_data_and_save()
                st.success(f"隊伍 '{new_team_name}' 的資料已更新！")
                st.rerun()

        # ... (其餘按鈕邏輯不變) ...
        with btn_cols[1]:
            if st.button(f"🔄 清空成員", key=f"clear_{idx}"):
                st.session_state.data["teams"][idx]["member"] = [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)]
                sync_data_and_save()
                st.success(f"隊伍 '{team['team_name']}' 的成員已清空！")
                st.rerun()
        with btn_cols[2]:
            if st.button(f"🗑️ 刪除隊伍", key=f"delete_{idx}"):
                deleted_name = st.session_state.data["teams"].pop(idx)["team_name"]
                sync_data_and_save()
                st.success(f"隊伍 '{deleted_name}' 已被刪除！")
                st.rerun()
        with btn_cols[3]:
            # 需要傳入更新後的 team object 給 build_team_text
            current_team_state = {
                "team_name": new_team_name,
                "boss_times": new_boss_times,
                "member": edited_df.to_dict('records')
            }
            team_text_to_copy = build_team_text(current_team_state)
            st.text_area("📋 複製組隊資訊", value=team_text_to_copy, key=f"copy_{idx}", height=150)

# --- 新增隊伍區 ---
st.header("➕ 建立新隊伍")
with st.form("add_team_form", clear_on_submit=True):
    new_team_name_input = st.text_input("新隊伍名稱", placeholder=f"例如：拉圖斯 {len(teams) + 1} 隊")
    submitted = st.form_submit_button("建立隊伍")
    if submitted and new_team_name_input:
        if "teams" not in st.session_state.data:
            st.session_state.data["teams"] = []
        st.session_state.data["teams"].append({
            "team_name": new_team_name_input,
            "boss_times": "",
            "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)]
        })
        sync_data_and_save()
        st.success(f"已成功建立新隊伍：{new_team_name_input}！")
        st.rerun()
    elif submitted:
        st.warning("請輸入隊伍名稱！")
