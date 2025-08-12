import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import re

# --- 基礎設定 ---
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
UNAVAILABLE_KEY = "__UNAVAILABLE__"

# 【新結構】使用 proposed_slots 字典來儲存隊長設定的時間
DEFAULT_SCHEDULE = {
    "proposed_slots": {}, # e.g., {"星期四 (08-07)": "21:00", "星期五 (08-08)": ""}
    "availability": {UNAVAILABLE_KEY: []},
    "final_time": ""
}

# --- 資料處理函式 ---
def load_data():
    firebase_url = st.secrets["firebase"]["url"]
    try:
        response = requests.get(firebase_url)
        if response.status_code == 200:
            data = response.json()
            if data is None: return {"teams": [], "members": {}}
            data.setdefault("teams", [])
            data.setdefault("members", {})
            for team in data["teams"]:
                if "boss_times" in team and "team_remark" not in team:
                    team["team_remark"] = team.pop("boss_times")
                else:
                    team.setdefault("team_remark", "")
                
                # 確保 schedule 和其子結構存在
                team.setdefault("schedule", DEFAULT_SCHEDULE.copy())
                team["schedule"].setdefault("proposed_slots", {})
                team["schedule"].setdefault("availability", {UNAVAILABLE_KEY: []})
                team["schedule"]["availability"].setdefault(UNAVAILABLE_KEY, [])

            return data
        else:
            st.error(f"❌ 無法從 Firebase 載入資料，狀態碼：{response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"❌ 載入資料時發生例外：{e}")
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
    final_time = team.get('schedule', {}).get('final_time')
    time_display = final_time if final_time else "時間待定"
    remark = team.get('team_remark', '')
    title = f"【{team['team_name']} 徵人】"
    time = f"時間：{time_display}"
    remark_text = f"備註：{remark}" if remark else ""
    members = []
    current_members = [m for m in team.get("member", []) if m.get("name")]
    for i, member in enumerate(current_members, 1):
        line = f"{i}. {member.get('level','')} {member.get('job','')} {member.get('name')}".strip()
        members.append(line)
    missing_count = MAX_TEAM_SIZE - len(current_members)
    member_text = "✅ 目前成員：\n" + "\n".join(members) if members else ""
    missing_text = f"📋 尚缺 {missing_count} 人，歡迎私訊！" if missing_count > 0 else "🎉 隊伍已滿，可先排後補！"
    result = "\n\n".join(filter(None, [title, time, remark_text, member_text, missing_text])).strip()
    return result


def get_week_range():
    today = datetime.today()
    days_since_thu = (today.weekday() - 3) % 7
    start_of_week = today - timedelta(days=days_since_thu)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%m/%d')} ~ {end_of_week.strftime('%m/%d')}"

# --- 【新功能】自動產生每週的日期列表 ---
def generate_weekly_schedule_days():
    """產生從本週四到下週二，包含中文星期與日期的列表"""
    today = datetime.today()
    days_since_thu = (today.weekday() - 3) % 7
    start_of_week = today - timedelta(days=days_since_thu)
    
    weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
    schedule_days = []
    # 循環 6 天 (週四到下週二)
    for i in range(6):
        current_day = start_of_week + timedelta(days=i)
        # 修正點：將日期的 / 換成 -，以符合 Firebase Key 的規範
        day_str = f"星期{weekdays_zh[current_day.weekday()]} ({current_day.strftime('%m-%d')})"
        schedule_days.append(day_str)
    return schedule_days

# --- 初始化 Session State & 同步函式 ---
if "data" not in st.session_state:
    st.session_state.data = load_data()

def sync_data_and_save():
    save_data(st.session_state.data)

# --- UI 介面 ---
st.title("🍁 Monarchs公會組隊系統 🍁")
with st.expander("📝 系統介紹與說明"):
    st.markdown( f"""
        ### 本周區間：{get_week_range()}
        #### **組隊流程**
        1.  **【註冊角色】** 在下方的 **👤 公會成員名冊** 註冊或更新你的角色資料。
        2.  **【加入隊伍】** 找到想加入的隊伍，在「成員名單」分頁中從下拉選單選擇你的名字，並 **【💾 儲存變更】**。
        3.  **【每週回報時間】**
            - 切換到「時間調查」分頁，在你想參加的時段，從下拉選單中 **選你的名字**。
            - 如果所有時段都 **無法配合**，請在最下方的選項中選你的名字。
            - 完成後點擊 **【💾 儲存時間回報】**。
        
        <span style="color:red;">※ 注意事項：每位成員每週以報名 1 組為原則；若需報名 2 組，請自行購買「突襲額外獎勵票券」。請勿報名後缺席，以免造成隊友困擾，感謝配合。</span>
    """, unsafe_allow_html=True)

st.header("👤 公會成員名冊")
with st.expander("點此註冊或更新你的個人資料"):
    all_members = st.session_state.data.get("members", {})
    member_list_for_select = [""] + sorted(list(all_members.keys()))
    selected_member_name = st.selectbox("選擇你的角色 (或留空以註冊新角色)", options=member_list_for_select, key="member_select_main")
    default_info = all_members.get(selected_member_name, {"job": "", "level": "", "atk": ""})
    with st.form("member_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        name = c1.text_input("遊戲ID", value=selected_member_name, disabled=bool(selected_member_name))
        job = c2.selectbox("職業", options=JOB_SELECT_LIST, index=JOB_SELECT_LIST.index(default_info.get("job")) if default_info.get("job") in JOB_SELECT_LIST else 0)
        level = c3.text_input("等級", value=default_info.get("level", ""))
        atk = c4.text_input("表攻 (乾表)", value=default_info.get("atk", ""))
        submit_col, delete_col = st.columns([4, 1])
        if submit_col.form_submit_button("💾 儲存角色資料", use_container_width=True):
            final_name = selected_member_name or name
            if not final_name: st.warning("請務必填寫遊戲ID！")
            else:
                st.session_state.data["members"][final_name] = {"job": job, "level": level, "atk": atk}
                sync_data_and_save()
                st.success(f"角色 '{final_name}' 的資料已儲存！")
                st.rerun()
        if selected_member_name and delete_col.form_submit_button("🗑️ 刪除此角色", use_container_width=True):
            del st.session_state.data["members"][selected_member_name]
            sync_data_and_save()
            st.success(f"角色 '{selected_member_name}' 已從名冊中刪除！")
            st.rerun()

# --- 當前隊伍名單 ---
st.header("📋 當前隊伍名單")
teams = st.session_state.data.get("teams", [])
all_members = st.session_state.data.get("members", {})
member_names_for_team_select = [""] + sorted(list(all_members.keys()))
WEEKLY_SCHEDULE_DAYS = generate_weekly_schedule_days() # 全域計算一次即可

for idx, team in enumerate(teams):
    if 'schedule' not in team: team['schedule'] = DEFAULT_SCHEDULE.copy()
    final_time = team.get('schedule', {}).get('final_time')
    expander_label = f"🍁 **{team['team_name']}**｜📅 **最終時間：{final_time}**" if final_time else f"🍁 **{team['team_name']}**｜⏰ 時間調查中..."
    
    with st.expander(expander_label):
        member_count = sum(1 for m in team.get("member", []) if m.get("name"))
        c1, c2 = st.columns([3, 1])
        c1.progress(member_count / MAX_TEAM_SIZE, text=f"👥 人數: {member_count} / {MAX_TEAM_SIZE}")
        c2.info(f"✨ 尚缺 {MAX_TEAM_SIZE - member_count} 人" if member_count < MAX_TEAM_SIZE else "🎉 人數已滿")
        st.markdown("---")
        
        tab1, tab2 = st.tabs(["**👥 成員名單**", "**🗓️ 時間調查**"])

        with tab1:
            with st.form(f"team_form_{idx}", clear_on_submit=False):
                c1, c2 = st.columns(2)
                team_name = c1.text_input("隊伍名稱", value=team["team_name"], key=f"name_{idx}")
                team_remark = c2.text_input("隊伍備註", value=team.get("team_remark", ""), key=f"remark_{idx}", help="主要時間請至「時間調查」分頁設定")
                st.write("**編輯隊伍成員 (請由名稱欄位選擇)：**")
                df = pd.DataFrame(team.get("member", [])).reindex(columns=['name', 'job', 'level', 'atk'], fill_value="")
                edited_df = st.data_editor(df, key=f"editor_{idx}", num_rows="fixed", use_container_width=True,column_config={"_index": None,"name": st.column_config.SelectboxColumn("名稱", options=member_names_for_team_select, required=False),"job": st.column_config.TextColumn("職業", disabled=True),"level": st.column_config.TextColumn("等級", disabled=True),"atk": st.column_config.TextColumn("表攻", disabled=True),},column_order=("name", "job", "level", "atk"))
                st.markdown("---")
                btn_cols = st.columns([2, 1, 1, 2])
                if btn_cols[0].form_submit_button(f"💾 儲存變更", type="primary", use_container_width=True):
                    updated_members = []
                    for _, row in edited_df.iterrows():
                        member_name = row["name"]
                        if member_name and member_name in all_members: updated_members.append({"name": member_name, **all_members[member_name]})
                        else: updated_members.append({"name": "", "job": "", "level": "", "atk": ""})
                    st.session_state.data["teams"][idx].update({"team_name": team_name, "team_remark": team_remark, "member": updated_members})
                    sync_data_and_save()
                    st.success(f"隊伍 '{team_name}' 的資料已更新！")
                    st.rerun()
                if btn_cols[1].form_submit_button(f"🔄 清空成員", use_container_width=True):
                    st.session_state.data["teams"][idx]["member"] = [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)]
                    sync_data_and_save()
                    st.success(f"隊伍 '{team['team_name']}' 的成員已清空！")
                    st.rerun()
                if btn_cols[2].form_submit_button(f"🗑️ 刪除隊伍", use_container_width=True):
                    deleted_name = st.session_state.data["teams"].pop(idx)["team_name"]
                    sync_data_and_save()
                    st.success(f"隊伍 '{deleted_name}' 已被刪除！")
                    st.rerun()
                with btn_cols[3]:
                    st.text_area("📋 複製組隊資訊", value=build_team_text(st.session_state.data["teams"][idx]), key=f"copy_{idx}", height=180, help="點此複製後可貼到 Discord")

        
        with tab2:
            schedule = team.get("schedule", DEFAULT_SCHEDULE.copy())
            
            # --- 【全新改版】步驟1：隊長設定時段 ---
            st.subheader("步驟1：隊長設定時段")
            proposed_slots = schedule.get("proposed_slots", {})

            with st.form(f"captain_time_form_{idx}"):
                st.info("請為希望調查的日期填上時間，留空則代表該日期不開放。")
                for day_string in WEEKLY_SCHEDULE_DAYS:
                    col1, col2 = st.columns([1, 2])
                    col1.markdown(f"**{day_string}**")
                    col2.text_input(
                        "時間", 
                        value=proposed_slots.get(day_string, ""), 
                        key=f"time_input_{idx}_{day_string}",
                        placeholder="例如: 21:00 或 晚上",
                        label_visibility="collapsed"
                    )
                
                if st.form_submit_button("💾 更新時段", type="primary", use_container_width=True):
                    old_availability = schedule.get("availability", {})
                    new_proposed_slots = {}
                    
                    for day_string in WEEKLY_SCHEDULE_DAYS:
                        time_val = st.session_state[f"time_input_{idx}_{day_string}"].strip()
                        new_proposed_slots[day_string] = time_val

                    # 從新設定的 slots 產生有效的時段列表
                    valid_new_times = [f"{day} {time}" for day, time in new_proposed_slots.items() if time]
                    
                    # 清理 availability，只保留在新時段列表中仍然有效的回報
                    cleaned_availability = { UNAVAILABLE_KEY: old_availability.get(UNAVAILABLE_KEY, []) }
                    for time_slot in valid_new_times:
                        if time_slot in old_availability:
                            cleaned_availability[time_slot] = old_availability[time_slot]

                    # 更新 session_state
                    st.session_state.data["teams"][idx]["schedule"]["proposed_slots"] = new_proposed_slots
                    st.session_state.data["teams"][idx]["schedule"]["availability"] = cleaned_availability

                    # 檢查最終時間是否還有效
                    current_final_time = schedule.get("final_time", "")
                    if current_final_time and current_final_time not in valid_new_times:
                        st.session_state.data["teams"][idx]["schedule"]["final_time"] = ""
                        st.toast(f"注意：原定的最終時間 '{current_final_time}' 已被移除，請重新選擇。")
                    
                    sync_data_and_save()
                    st.success("時段已更新！")
                    st.rerun()

            st.markdown("---")
            st.subheader("步驟2：成員填寫")
            
            # 動態產生有效的調查時段列表供後續使用
            valid_proposed_times = [f"{day} {time}" for day, time in proposed_slots.items() if time]
            
            current_team_members = sorted([m['name'] for m in team['member'] if m.get('name')])
            availability = schedule.get("availability", {})

            if current_team_members and valid_proposed_times:
                all_team_members_set = set(current_team_members)
                responded_members_set = set(name for member_list in availability.values() for name in member_list)
                unresponsive_members = sorted(list(all_team_members_set - responded_members_set))
                if unresponsive_members:
                    st.info(f"📋 **尚未回報時間的成員：** {', '.join(unresponsive_members)}")
                else:
                    st.success("🎉 **所有成員皆已回報時間！**")
                st.markdown("---")

            if not current_team_members: st.warning("隊伍中尚無成員，請先至「成員名單」分頁加入。")
            elif not valid_proposed_times: st.warning("隊長尚未設定任何有效的時段。")
            else:
                with st.form(f"availability_form_{idx}"):
                    # 使用動態產生的列表來顯示
                    for time_slot in valid_proposed_times:
                        c1, c2, c3 = st.columns([1.5, 2, 0.8])
                        c1.markdown(f"**{time_slot}**")
                        default_selection = [name for name in availability.get(time_slot, []) if name in current_team_members]
                        c2.multiselect("可到場成員", options=current_team_members, default=default_selection, key=f"ms_{idx}_{time_slot}", label_visibility="collapsed")
                        c3.metric("可到場人數", f"{len(st.session_state[f'ms_{idx}_{time_slot}'])} / {len(current_team_members)}")
                    st.markdown("---")
                    c1, c2 = st.columns([1.5, 2.8])
                    c1.markdown("**<font color='orange'>都無法配合</font>**", unsafe_allow_html=True)
                    default_unavailable = [name for name in availability.get(UNAVAILABLE_KEY, []) if name in current_team_members]
                    c2.multiselect("勾選此處表示以上時間皆無法配合", options=current_team_members, default=default_unavailable, key=f"ms_{idx}_{UNAVAILABLE_KEY}", label_visibility="collapsed")
                    
                    if st.form_submit_button("💾 儲存時間回報", type="primary", use_container_width=True):
                        new_availability = {}
                        all_attending_members = set()
                        for time_slot in valid_proposed_times:
                            selections = st.session_state[f"ms_{idx}_{time_slot}"]
                            new_availability[time_slot] = selections
                            all_attending_members.update(selections)
                        unavailable_selections = st.session_state[f"ms_{idx}_{UNAVAILABLE_KEY}"]
                        new_availability[UNAVAILABLE_KEY] = [name for name in unavailable_selections if name not in all_attending_members]
                        st.session_state.data["teams"][idx]["schedule"]["availability"] = new_availability
                        sync_data_and_save()
                        st.success("時間回報已成功儲存！")
                        st.rerun()

            st.markdown("---")
            st.subheader("步驟3：確認最終時間")
            unavailable_list = availability.get(UNAVAILABLE_KEY, [])
            if unavailable_list: st.warning(f"**已確認無法參加：** {', '.join(unavailable_list)}")
            if not valid_proposed_times: st.info("設定時段後，此處可選擇最終開打時間。")
            else:
                with st.form(f"final_time_form_{idx}"):
                    options = ["尚未決定"] + [f"{ts} ({len(availability.get(ts, []))}人可)" for ts in valid_proposed_times]
                    current_final = schedule.get("final_time")
                    current_idx = 0
                    if current_final:
                        try: current_idx = [opt.startswith(current_final) for opt in options].index(True)
                        except ValueError: pass
                    selected_str = st.selectbox("隊長確認時間", options=options, index=current_idx, key=f"final_time_{idx}")
                    if st.form_submit_button("✅ 確認最終時間", use_container_width=True):
                        final_time_to_save = ""
                        if selected_str != "尚未決定":
                            match = re.match(r"^(.*?)\s*\(\d+人可\)$", selected_str)
                            if match:
                                final_time_to_save = match.group(1).strip()
                        st.session_state.data["teams"][idx]["schedule"]["final_time"] = final_time_to_save
                        sync_data_and_save()
                        st.success(f"最終時間已確認為：{final_time_to_save or '尚未決定'}")
                        st.rerun()

# --- 新增隊伍區 ---
st.header("➕ 建立新隊伍")
with st.form("add_team_form", clear_on_submit=True):
    new_team_name_input = st.text_input("新隊伍名稱", placeholder=f"例如：拉圖斯 {len(teams) + 1} 隊")
    if st.form_submit_button("建立隊伍"):
        if new_team_name_input:
            st.session_state.data.setdefault("teams", []).append({
                "team_name": new_team_name_input, "team_remark": "", 
                "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)],
                "schedule": DEFAULT_SCHEDULE.copy()
            })
            sync_data_and_save()
            st.success(f"已成功建立新隊伍：{new_team_name_input}！")
            st.rerun()
        else: st.warning("請輸入隊伍名稱！")
