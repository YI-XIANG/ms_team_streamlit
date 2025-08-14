import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
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

# --- 核心函式 ---
def get_start_of_week(base_date: date) -> date:
    """計算給定日期所在週的星期四是哪一天"""
    days_since_thu = (base_date.weekday() - 3) % 7
    return base_date - timedelta(days=days_since_thu)

def get_default_schedule():
    """回傳一個全新的、獨立的預設排程字典，並包含當前的週次開始日期"""
    return {
        "proposed_slots": {},
        "availability": {UNAVAILABLE_KEY: []},
        "final_time": "",
        "schedule_start_date": get_start_of_week(date.today()).strftime('%Y-%m-%d')
    }

def load_data():
    """從 Firebase 載入資料，並確保所有隊伍都有完整的資料結構"""
    firebase_url = st.secrets["firebase"]["url"]
    try:
        response = requests.get(f"{firebase_url}.json")
        response.raise_for_status()
        data = response.json()
        if data is None: return {"teams": [], "members": {}}
        
        data.setdefault("teams", [])
        data.setdefault("members", {})

        for team in data["teams"]:
            if "boss_times" in team and "team_remark" not in team:
                team["team_remark"] = team.pop("boss_times")
            else:
                team.setdefault("team_remark", "")
            
            if "schedule" not in team:
                team["schedule"] = get_default_schedule()
            
            default_sched = get_default_schedule()
            for key, value in default_sched.items():
                team["schedule"].setdefault(key, value)
            # 確保舊資料也有 "無法配合" 的鍵
            team["schedule"].setdefault("availability", {}).setdefault(UNAVAILABLE_KEY, [])

        return data
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 無法從 Firebase 載入資料，網路錯誤：{e}")
    except Exception as e:
        st.error(f"❌ 載入資料時發生未預期的錯誤：{e}")
    return {"teams": [], "members": {}}

def save_data(data):
    """將資料儲存到 Firebase"""
    firebase_url = st.secrets["firebase"]["url"]
    try:
        response = requests.put(f"{firebase_url}.json", json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 儲存資料時發生網路錯誤：{e}")
    except Exception as e:
        st.error(f"❌ 儲存資料時發生未預期的錯誤：{e}")

def build_team_text(team):
    """產生用於複製到 Discord 的組隊資訊文字"""
    final_time = team.get('schedule', {}).get('final_time')
    time_display = final_time if final_time else "時間待定"
    remark = team.get('team_remark', '')
    title = f"【{team['team_name']} 徵人】"
    time = f"時間：{time_display}"
    remark_text = f"備註：{remark}" if remark else ""
    
    current_members = [m for m in team.get("member", []) if m.get("name")]
    members_lines = [
        f"{i}. {member.get('level','')} {member.get('job','')} {member.get('name')}".strip()
        for i, member in enumerate(current_members, 1)
    ]
    member_text = "✅ 目前成員：\n" + "\n".join(members_lines) if members_lines else ""
    
    missing_count = MAX_TEAM_SIZE - len(current_members)
    missing_text = f"📋 尚缺 {missing_count} 人，歡迎私訊！" if missing_count > 0 else "🎉 隊伍已滿，可先排後補！"
    
    return "\n\n".join(filter(None, [title, time, remark_text, member_text, missing_text])).strip()

def get_week_range(base_date: date) -> str:
    """計算並回傳指定日期所在週的週四到下週三的日期區間"""
    start_of_week = get_start_of_week(base_date)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%m/%d')} ~ {end_of_week.strftime('%m/%d')}"

def generate_weekly_schedule_days(start_date: date) -> list[str]:
    """產生從指定日期開始的一週排程列表（週四到下週三）"""
    start_of_week = get_start_of_week(start_date)
    weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
    schedule_days = [f"星期{weekdays_zh[(start_of_week + timedelta(days=i)).weekday()]} ({(start_of_week + timedelta(days=i)).strftime('%m-%d')})" for i in range(7)]
    return schedule_days

def update_team_schedule_week(team_index: int, new_base_date: date):
    """更新指定隊伍的排程到新的一週，並重置相關設定"""
    new_start_of_week = get_start_of_week(new_base_date)
    new_week_days = generate_weekly_schedule_days(start_date=new_start_of_week)
    
    new_schedule = get_default_schedule()
    new_schedule["schedule_start_date"] = new_start_of_week.strftime('%Y-%m-%d')
    new_schedule["proposed_slots"] = {day: "" for day in new_week_days}
    
    st.session_state.data["teams"][team_index]["schedule"] = new_schedule
    sync_data_and_save()
    st.toast("時段已更新！頁面即將刷新...")

# --- 初始化 Session State & 同步函式 ---
if "data" not in st.session_state:
    st.session_state.data = load_data()

def sync_data_and_save():
    save_data(st.session_state.data)

# --- UI 介面 ---
st.title("🍁 Monarchs公會組隊系統 🍁")
with st.expander("📝 系統介紹與說明"):
    st.markdown( f"""
        ### 本週區間：{get_week_range(date.today())}
        #### **組隊流程**
        1.  **【註冊角色】** 在下方的 **👤 公會成員表** 註冊或更新你的角色資料。
        2.  **【加入隊伍】** 找到想加入的隊伍，在「成員名單」分頁中從下拉選單選擇你的名字，並 **【💾 儲存變更】**。
        3.  **【每週回報時間】**
            - 在「時間調查」分頁，可使用 **◀️** 和 **▶️** 按鈕切換【本週】與【下週】時段。
            - **隊長**在「步驟1」設定該週可行的時段。
            - **隊員**在「步驟2」勾選自己可以的時間。
        
        <span style="color:red;">※ 注意事項：切換週次會重置該隊伍的時間設定與回報。每位成員每週以報名 1 組為原則。</span>
    """, unsafe_allow_html=True)

st.header("👤 公會成員表")
with st.expander("點此註冊或更新你的個人資料"):
    all_members = st.session_state.data.get("members", {})
    member_list_for_select = [""] + sorted(list(all_members.keys()))
    selected_member_name = st.selectbox("選擇你的角色 (或留空以註冊新角色)", options=member_list_for_select, key="member_select_main")
    
    default_info = all_members.get(selected_member_name, {"job": "", "level": "", "atk": ""})
    job_index = JOB_SELECT_LIST.index(default_info["job"]) if default_info.get("job") in JOB_SELECT_LIST else 0
    
    with st.form("member_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        name_input = c1.text_input("遊戲ID", value=selected_member_name, disabled=bool(selected_member_name), help="註冊新角色時請在此填寫ID，選擇舊角色則此欄不可編輯。")
        job_input = c2.selectbox("職業", options=JOB_SELECT_LIST, index=job_index)
        level_input = c3.text_input("等級", value=default_info.get("level", ""))
        atk_input = c4.text_input("表攻 (乾表)", value=default_info.get("atk", ""))
        
        submit_col, delete_col = st.columns([4, 1])
        if submit_col.form_submit_button("💾 儲存角色資料", use_container_width=True):
            final_name = selected_member_name or name_input.strip()
            if not final_name: 
                st.warning("請務必填寫遊戲ID！")
            else:
                st.session_state.data["members"][final_name] = {"job": job_input, "level": level_input, "atk": atk_input}
                sync_data_and_save()
                st.success(f"角色 '{final_name}' 的資料已儲存！")
                st.rerun()
        
        if selected_member_name and delete_col.form_submit_button("🗑️ 刪除此角色", use_container_width=True):
            del st.session_state.data["members"][selected_member_name]
            for team_idx in range(len(st.session_state.data['teams'])):
                 st.session_state.data['teams'][team_idx]['member'] = [m for m in st.session_state.data['teams'][team_idx].get('member', []) if m.get('name') != selected_member_name]
            sync_data_and_save()
            st.success(f"角色 '{selected_member_name}' 已從名冊中刪除！")
            st.rerun()

st.header("📋 隊伍名單")
teams = st.session_state.data.get("teams", [])
all_members = st.session_state.data.get("members", {})
member_names_for_team_select = [""] + sorted(list(all_members.keys()))

for idx, team in enumerate(teams):
    schedule = team.get("schedule", get_default_schedule())
    final_time = schedule.get('final_time')
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
                current_members_list = team.get("member", [])
                if len(current_members_list) != MAX_TEAM_SIZE:
                    current_members_list.extend([{"name": "", "job": "", "level": "", "atk": ""}] * (MAX_TEAM_SIZE - len(current_members_list)))
                    current_members_list = current_members_list[:MAX_TEAM_SIZE]

                df = pd.DataFrame(current_members_list).reindex(columns=['name', 'job', 'level', 'atk'], fill_value="")
                edited_df = st.data_editor(df, key=f"editor_{idx}", num_rows="fixed", use_container_width=True,
                                           column_config={
                                               "_index": None, "name": st.column_config.SelectboxColumn("名稱", options=member_names_for_team_select, required=False),
                                               "job": st.column_config.TextColumn("職業", disabled=True), "level": st.column_config.TextColumn("等級", disabled=True),
                                               "atk": st.column_config.TextColumn("表攻", disabled=True),
                                           }, column_order=("name", "job", "level", "atk"))
                
                st.markdown("---")
                btn_cols = st.columns([2, 1, 1, 2])
                if btn_cols[0].form_submit_button(f"💾 儲存變更", type="primary", use_container_width=True):
                    updated_members = [{"name": row["name"], **all_members.get(row["name"], {})} if row["name"] else {"name": "", "job": "", "level": "", "atk": ""} for _, row in edited_df.iterrows()]
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
            schedule_start_date_str = schedule.get("schedule_start_date", get_start_of_week(date.today()).strftime('%Y-%m-%d'))
            schedule_base_date = datetime.strptime(schedule_start_date_str, '%Y-%m-%d').date()
            
            today = date.today()
            start_of_this_week = get_start_of_week(today)
            start_of_next_week = start_of_this_week + timedelta(days=7)
            
            is_this_week = (schedule_base_date == start_of_this_week)
            is_next_week = (schedule_base_date == start_of_next_week)
            
            displayed_schedule_days = generate_weekly_schedule_days(start_date=schedule_base_date)

            st.markdown("---")
            st.subheader(f"步驟1：隊長設定時段，🗓️ **目前顯示時段：{get_week_range(schedule_base_date)}**")

            info_col, btn1_col, btn2_col = st.columns([2, 1, 1])
  
            with info_col:
                st.info("請【隊長】在右方切換週次後，於下方填寫時間。")

            if btn1_col.button("◀️ 返回本週", key=f"this_week_{idx}", use_container_width=True, help="返回本週時段，將會重置目前的時間與回報。"):
                if is_this_week:
                    st.toast("已經是本週時段了！")
                else:
                    update_team_schedule_week(idx, today)
                    st.rerun()

            if btn2_col.button("前往下週 ▶️", key=f"next_week_{idx}", use_container_width=True, help="前往下週時段，將會重置目前的時間與回報。"):
                if is_next_week:
                    st.toast("已是下週時段，無法再前進。")
                else:
                    update_team_schedule_week(idx, today + timedelta(days=7))
                    st.rerun()
            
            proposed_slots = schedule.get("proposed_slots", {})
            with st.form(f"captain_time_form_{idx}"):
                for day_string in displayed_schedule_days:
                    col1, col2 = st.columns([1, 2])
                    col1.markdown(f"**{day_string}**")
                    col2.text_input("時間", value=proposed_slots.get(day_string, ""), key=f"time_input_{idx}_{day_string}", placeholder="例如: 21:00 或 晚上", label_visibility="collapsed")
                
                if st.form_submit_button("💾 更新時段", type="primary", use_container_width=True):
                    new_proposed_slots = {day_string: st.session_state[f"time_input_{idx}_{day_string}"].strip() for day_string in displayed_schedule_days}
                    st.session_state.data["teams"][idx]["schedule"]["proposed_slots"] = new_proposed_slots
                    # 當隊長更新時段後，清空舊的回報，避免資料錯亂
                    st.session_state.data["teams"][idx]["schedule"]["availability"] = {UNAVAILABLE_KEY: []}
                    st.session_state.data["teams"][idx]["schedule"]["final_time"] = ""
                    sync_data_and_save()
                    st.success("時段已更新，舊的回報已清除！")
                    st.rerun()

            st.markdown("---")
            st.subheader("步驟2：成員填寫")
            valid_proposed_times = [f"{day} {time}" for day in displayed_schedule_days if (time := proposed_slots.get(day))]
            current_team_members = sorted([m['name'] for m in team['member'] if m.get('name')])
            availability = schedule.get("availability", {})

            if not current_team_members: st.warning("隊伍中尚無成員，請先至「成員名單」分頁加入。")
            elif not valid_proposed_times: st.warning("隊長尚未設定任何有效的時段。")
            else:
                with st.form(f"availability_form_{idx}"):
                    # --- 修正點 START ---
                    # 這裡的邏輯是修正的核心，確保UI總是反映已儲存的狀態
                    
                    # 用於在表單提交後，暫存使用者在UI上的選擇
                    form_selections = {}

                    for time_slot in valid_proposed_times:
                        c1, c2, c3 = st.columns([1.5, 2, 0.8])
                        c1.markdown(f"**{time_slot}**")
                        
                        # 1. 從可靠的資料來源 (availability) 取得已儲存的預設值
                        #    過濾掉已經不在隊伍中的成員，以防資料陳舊
                        saved_selection = [name for name in availability.get(time_slot, []) if name in current_team_members]
                        
                        # 2. 使用 multiselect 的 'default' 參數來設定預設值
                        #    將元件的 key 和變數分開，避免混淆
                        #    元件的回傳值是使用者當前在UI上的選擇
                        current_selection = c2.multiselect(
                            "可到場成員", 
                            options=current_team_members, 
                            default=saved_selection, # << 關鍵修正！
                            key=f"ms_{idx}_{time_slot}", 
                            label_visibility="collapsed"
                        )
                        
                        # 將當前的選擇存起來，以便提交時使用
                        form_selections[time_slot] = current_selection

                        # 3. 人數統計直接使用元件的回傳值，可以即時反應UI上的變化
                        c3.metric("可到場人數", f"{len(current_selection)} / {len(current_team_members)}")
                    
                    st.markdown("---")
                    c1, c2 = st.columns([1.5, 2.8])
                    c1.markdown("**<font color='orange'>都無法配合</font>**", unsafe_allow_html=True)
                    
                    # 同樣地，為「無法配合」的選項設定正確的預設值
                    saved_unavailable = [name for name in availability.get(UNAVAILABLE_KEY, []) if name in current_team_members]
                    unavailable_selection = c2.multiselect(
                        "勾選此處表示以上時間皆無法配合", 
                        options=current_team_members, 
                        default=saved_unavailable, # << 關鍵修正！
                        key=f"ms_{idx}_{UNAVAILABLE_KEY}", 
                        label_visibility="collapsed"
                    )
                    form_selections[UNAVAILABLE_KEY] = unavailable_selection

                    # --- 修正點 END ---
                    
                    if st.form_submit_button("💾 儲存時間回報", type="primary", use_container_width=True):
                        # 提交表單時，我們從 st.session_state 讀取由表單提交的最終值
                        new_availability = {}
                        all_attending_members = set()
                        
                        for time_slot in valid_proposed_times:
                            # 讀取表單提交後，存在 st.session_state 的值
                            selections = st.session_state[f"ms_{idx}_{time_slot}"]
                            new_availability[time_slot] = selections
                            all_attending_members.update(selections)
                        
                        # 處理無法配合的人員，確保他們沒有同時勾選其他可到場時間
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
                    current_idx = next((i for i, opt in enumerate(options) if opt.startswith(current_final)), 0) if current_final else 0
                    
                    selected_str = st.selectbox("隊長確認時間", options=options, index=current_idx, key=f"final_time_{idx}")
                    if st.form_submit_button("✅ 確認最終時間", use_container_width=True):
                        final_time_to_save = ""
                        if selected_str != "尚未決定":
                            match = re.match(r"^(.*?)\s*\(\d+人可\)$", selected_str)
                            if match: final_time_to_save = match.group(1).strip()
                        
                        st.session_state.data["teams"][idx]["schedule"]["final_time"] = final_time_to_save
                        sync_data_and_save()
                        st.success(f"最終時間已確認為：{final_time_to_save or '尚未決定'}")
                        st.rerun()

st.header("➕ 建立新隊伍")
with st.form("add_team_form", clear_on_submit=True):
    new_team_name_input = st.text_input("新隊伍名稱", placeholder=f"例如：拉圖斯 {len(teams) + 1} 隊")
    if st.form_submit_button("建立隊伍"):
        if new_team_name_input:
            new_schedule = get_default_schedule()
            new_schedule["proposed_slots"] = {day: "" for day in generate_weekly_schedule_days(date.today())}

            st.session_state.data.setdefault("teams", []).append({
                "team_name": new_team_name_input, "team_remark": "",
                "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)],
                "schedule": new_schedule
            })
            sync_data_and_save()
            st.success(f"已成功建立新隊伍：{new_team_name_input}！")
            st.rerun()
        else:
            st.warning("請輸入隊伍名稱！")
