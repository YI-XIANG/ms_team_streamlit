import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
import re
import json

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

def get_default_schedule_for_week():
    """回傳一週行程的預設資料結構"""
    return {
        "proposed_slots": {},
        "availability": {UNAVAILABLE_KEY: []},
        "final_time": "",
    }

def load_data():
    """從 Firebase 載入、遷移並驗證資料結構"""
    firebase_url = st.secrets["firebase"]["url"]
    try:
        response = requests.get(f"{firebase_url}.json")
        response.raise_for_status()
        data = response.json()

        if data is None:
            return {"teams": [], "members": {}}

        data.setdefault("teams", [])
        data.setdefault("members", {})

        today = date.today()
        start_of_this_week = get_start_of_week(today)
        start_of_this_week_str = start_of_this_week.strftime('%Y-%m-%d')
        start_of_next_week_str = (start_of_this_week + timedelta(days=7)).strftime('%Y-%m-%d')
        valid_week_keys = {start_of_this_week_str, start_of_next_week_str}

        for team in data["teams"]:
            # 資料結構遷移：舊的 schedule -> 新的 schedules
            if "schedule" in team and "schedules" not in team:
                old_schedule = team.pop("schedule")
                start_date_key = old_schedule.pop("schedule_start_date", start_of_this_week_str)
                team["schedules"] = {start_date_key: old_schedule}

            team.setdefault("schedules", {})

            # 清理過期的週次資料
            current_schedules = team.get("schedules", {})
            managed_schedules = {key: value for key, value in current_schedules.items() if key in valid_week_keys}

            # ### 【健壯性優化】 ###
            # 確保本週與下週的行程資料存在且結構完整
            for week_key in valid_week_keys:
                if week_key not in managed_schedules:
                    managed_schedules[week_key] = get_default_schedule_for_week()
                else:
                    # 確保即使週次存在，其內部結構也是完整的
                    managed_schedules[week_key].setdefault("proposed_slots", {})
                    managed_schedules[week_key].setdefault("availability", {UNAVAILABLE_KEY: []})
                    managed_schedules[week_key].setdefault("final_time", "")

            team["schedules"] = managed_schedules

            # 資料結構遷移：舊的 boss_times -> 新的 team_remark
            if "boss_times" in team and "team_remark" not in team:
                team["team_remark"] = team.pop("boss_times")
            else:
                team.setdefault("team_remark", "")

        return data

    except requests.exceptions.RequestException as e:
        st.error(f"❌ 無法從 Firebase 載入資料，網路錯誤：{e}")
    except Exception as e:
        st.error(f"❌ 載入資料時發生未預期的錯誤：{e}, {e.__traceback__.tb_lineno}")

    return {"teams": [], "members": {}}

def save_data(data):
    """將資料儲存到 Firebase"""
    firebase_url = st.secrets["firebase"]["url"]
    try:
        # 使用 ensure_ascii=False 來正確處理中文字元
        response = requests.put(f"{firebase_url}.json", data=json.dumps(data, ensure_ascii=False).encode('utf-8'))
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 儲存資料時發生網路錯誤：{e}")
    except Exception as e:
        st.error(f"❌ 儲存資料時發生未預期的錯誤：{e}")

def build_team_text(team):
    """產生用於複製到 Discord 的隊伍資訊文字"""
    today = date.today()
    start_of_this_week_str = get_start_of_week(today).strftime('%Y-%m-%d')
    this_week_schedule = team.get('schedules', {}).get(start_of_this_week_str, {})
    final_time = this_week_schedule.get('final_time', '')
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
    """產生週次的日期範圍字串，例如 '08/14 ~ 08/20'"""
    start_of_week = get_start_of_week(base_date)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%m/%d')} ~ {end_of_week.strftime('%m/%d')}"

def generate_weekly_schedule_days(start_date: date) -> list[str]:
    """根據開始日期產生一週七天的字串列表"""
    start_of_week = get_start_of_week(start_date)
    weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
    schedule_days = [
        f"星期{weekdays_zh[(start_of_week + timedelta(days=i)).weekday()]} ({(start_of_week + timedelta(days=i)).strftime('%m-%d')})"
        for i in range(7)
    ]
    return schedule_days

# --- 初始化 Session State & 同步函式 ---
if "data" not in st.session_state:
    st.session_state.data = load_data()

if "team_view_week" not in st.session_state:
    st.session_state.team_view_week = {}

def sync_data_and_save():
    """將 session state 中的資料儲存到 Firebase"""
    save_data(st.session_state.data)

# --- UI 介面 ---
st.title("🍁 Monarchs公會組隊系統 🍁")

with st.expander("📝 系統介紹與說明"):
    st.markdown(
        f"""
        ### 本週區間：{get_week_range(date.today())}
        #### **組隊流程**
        1. **【註冊角色】** 在下方的 **👤 公會成員表** 註冊或更新你的角色資料。
        2. **【加入隊伍】** 找到想加入的隊伍，在「成員名單」分頁中從下拉選單選擇你的名字，並 **【💾 儲存變更】**。
        3. **【每週回報時間】**
           - 在「時間調查」分頁，可使用 **◀️** 和 **▶️** 按鈕切換【本週】與【下週】時段。**切換週次不會清除已填寫的資料**。
           - **隊長**在「步驟1」設定該週可行的時段。若時段未變更，成員回報不會被重置；若只修改部分時段，也僅有被修改的時段會重置回報。
           - **隊員**在「步驟2」勾選自己可以的時間。
        <span style="color:red;">※ 注意事項：系統會自動管理本週與下週的資料，每週四凌晨會自動輪替。</span>
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
            # 同步刪除隊伍中的成員
            for team_idx in range(len(st.session_state.data['teams'])):
                st.session_state.data['teams'][team_idx]['member'] = [
                    m for m in st.session_state.data['teams'][team_idx].get('member', []) if m.get('name') != selected_member_name
                ]
            sync_data_and_save()
            st.success(f"角色 '{selected_member_name}' 已從名冊中刪除！")
            st.rerun()


st.header("📋 隊伍名單")
teams = st.session_state.data.get("teams", [])
all_members = st.session_state.data.get("members", {})
member_names_for_team_select = [""] + sorted(list(all_members.keys()))

today = date.today()
start_of_this_week = get_start_of_week(today)
start_of_this_week_str = start_of_this_week.strftime('%Y-%m-%d')
start_of_next_week_str = (start_of_this_week + timedelta(days=7)).strftime('%Y-%m-%d')


for idx, team in enumerate(teams):
    if idx not in st.session_state.team_view_week:
        st.session_state.team_view_week[idx] = start_of_this_week_str

    view_week_start_str = st.session_state.team_view_week[idx]
    view_week_start_date = datetime.strptime(view_week_start_str, '%Y-%m-%d').date()

    schedule_to_display = team.get("schedules", {}).get(view_week_start_str, get_default_schedule_for_week())
    final_time = schedule_to_display.get('final_time')

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
                     current_members_list.extend([{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE - len(current_members_list))])
                current_members_list = current_members_list[:MAX_TEAM_SIZE]

                df = pd.DataFrame(current_members_list).reindex(columns=['name', 'job', 'level', 'atk'], fill_value="")

                edited_df = st.data_editor(df, key=f"editor_{idx}", num_rows="fixed", use_container_width=True,
                    column_config={
                        "_index": None,
                        "name": st.column_config.SelectboxColumn("名稱", options=member_names_for_team_select, required=False),
                        "job": st.column_config.TextColumn("職業", disabled=True),
                        "level": st.column_config.TextColumn("等級", disabled=True),
                        "atk": st.column_config.TextColumn("表攻", disabled=True),
                    },
                    column_order=("name", "job", "level", "atk")
                )
                st.markdown("---")

                btn_cols = st.columns([2, 1, 1, 2])
                if btn_cols[0].form_submit_button(f"💾 儲存變更", type="primary", use_container_width=True):
                    updated_members = [
                        {"name": row["name"], **all_members.get(row["name"], {})} if row["name"] else {"name": "", "job": "", "level": "", "atk": ""}
                        for _, row in edited_df.iterrows()
                    ]
                    st.session_state.data["teams"][idx].update({
                        "team_name": team_name,
                        "team_remark": team_remark,
                        "member": updated_members
                    })
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
            displayed_schedule_days = generate_weekly_schedule_days(start_date=view_week_start_date)
            st.markdown("---")
            st.subheader(f"步驟1：隊長設定時段，🗓️ **目前顯示時段：{get_week_range(view_week_start_date)}**")
            info_col, btn1_col, btn2_col = st.columns([2, 1, 1])

            with info_col:
                is_this_week = view_week_start_str == start_of_this_week_str
                st.info("點擊右方按鈕切換【本週】與【下週】時段。")
            if btn1_col.button("◀️ 返回本週", key=f"this_week_{idx}", use_container_width=True, disabled=is_this_week):
                st.session_state.team_view_week[idx] = start_of_this_week_str
                st.rerun()
            if btn2_col.button("前往下週 ▶️", key=f"next_week_{idx}", use_container_width=True, disabled=not is_this_week):
                st.session_state.team_view_week[idx] = start_of_next_week_str
                st.rerun()

            old_proposed_slots = schedule_to_display.get("proposed_slots", {})
            current_availability = schedule_to_display.get("availability", {})

            with st.form(f"captain_time_form_{idx}_{view_week_start_str}"): # 加上週次確保 key 唯一
                for day_string in displayed_schedule_days:
                    col1, col2 = st.columns([1, 2])
                    col1.markdown(f"**{day_string}**")
                    col2.text_input("時間",
                                    value=old_proposed_slots.get(day_string, ""),
                                    key=f"time_input_{idx}_{view_week_start_str}_{day_string}",
                                    placeholder="例如: 21:00 或 晚上",
                                    label_visibility="collapsed")

                if st.form_submit_button("💾 更新時段", type="primary", use_container_width=True):
                    new_proposed_slots = {
                        day: st.session_state[f"time_input_{idx}_{view_week_start_str}_{day}"].strip()
                        for day in displayed_schedule_days
                    }

                    if new_proposed_slots == old_proposed_slots:
                        st.toast("時段沒有變更，無需更新。")
                    else:
                        updated_availability = {UNAVAILABLE_KEY: current_availability.get(UNAVAILABLE_KEY, [])}
                        for day in displayed_schedule_days:
                            old_time = old_proposed_slots.get(day, "")
                            new_time = new_proposed_slots.get(day, "")
                            if old_time == new_time:
                                if old_time:
                                    old_slot_key = f"{day} {old_time}"
                                    updated_availability[old_slot_key] = current_availability.get(old_slot_key, [])
                            else:
                                if new_time:
                                    new_slot_key = f"{day} {new_time}"
                                    updated_availability[new_slot_key] = []

                        data_path = st.session_state.data["teams"][idx]["schedules"][view_week_start_str]
                        data_path["proposed_slots"] = new_proposed_slots
                        data_path["availability"] = updated_availability
                        data_path["final_time"] = ""
                        sync_data_and_save()
                        st.success("時段已更新！有變更的時段之成員回報已被重置。")
                        st.rerun()

            st.markdown("---")
            st.subheader("步驟2：成員填寫")
            # 使用 `old_proposed_slots` 來建構選項是正確的，因為它反映了當前頁面上顯示的內容
            valid_proposed_times = [f"{day} {time}" for day in displayed_schedule_days if (time := old_proposed_slots.get(day))]
            current_team_members = sorted([m['name'] for m in team['member'] if m.get('name')])

            if not current_team_members:
                st.warning("隊伍中尚無成員，請先至「成員名單」分頁加入。")
            elif not valid_proposed_times:
                st.warning("隊長尚未設定任何有效的時段。")
            else:
                with st.form(f"availability_form_{idx}_{view_week_start_str}"): # 加上週次確保 key 唯一
                    for time_slot in valid_proposed_times:
                        c1, c2, c3 = st.columns([1.5, 2, 0.8])
                        c1.markdown(f"**{time_slot}**")
                        saved_selection = [name for name in current_availability.get(time_slot, []) if name in current_team_members]
                        current_selection = c2.multiselect("可到場成員", options=current_team_members, default=saved_selection, key=f"ms_{idx}_{view_week_start_str}_{time_slot}", label_visibility="collapsed")
                        c3.metric("可到場人數", f"{len(current_selection)} / {len(current_team_members)}")
                    st.markdown("---")

                    c1, c2 = st.columns([1.5, 2.8])
                    c1.markdown("**<font color='orange'>都無法配合</font>**", unsafe_allow_html=True)
                    saved_unavailable = [name for name in current_availability.get(UNAVAILABLE_KEY, []) if name in current_team_members]
                    unavailable_selection = c2.multiselect("勾選此處表示以上時間皆無法配合", options=current_team_members, default=saved_unavailable, key=f"ms_{idx}_{view_week_start_str}_{UNAVAILABLE_KEY}", label_visibility="collapsed")

                    if st.form_submit_button("💾 儲存時間回報", type="primary", use_container_width=True):
                        new_availability = {}
                        all_attending_members = set()
                        for time_slot in valid_proposed_times:
                            selections = st.session_state[f"ms_{idx}_{view_week_start_str}_{time_slot}"]
                            new_availability[time_slot] = selections
                            all_attending_members.update(selections)

                        unavailable_selections = st.session_state[f"ms_{idx}_{view_week_start_str}_{UNAVAILABLE_KEY}"]
                        new_availability[UNAVAILABLE_KEY] = [name for name in unavailable_selections if name not in all_attending_members]

                        data_path = st.session_state.data["teams"][idx]["schedules"][view_week_start_str]

                        # ### 【錯誤修復】 ###
                        # 使用 .setdefault() 來確保 "availability" 鍵一定存在，避免 KeyError。
                        # 即使 load_data 已做過防護，此處多一道防線可讓程式更健壯。
                        availability_dict = data_path.setdefault("availability", {UNAVAILABLE_KEY: []})
                        availability_dict.update(new_availability)

                        sync_data_and_save()
                        st.success("時間回報已成功儲存！")
                        st.rerun()

            st.markdown("---")
            st.subheader("步驟3：確認最終時間")
            unavailable_list = current_availability.get(UNAVAILABLE_KEY, [])
            if unavailable_list:
                st.warning(f"**已確認無法參加：** {', '.join(unavailable_list)}")

            if not valid_proposed_times:
                st.info("設定時段後，此處可選擇最終開打時間。")
            else:
                with st.form(f"final_time_form_{idx}_{view_week_start_str}"): # 加上週次確保 key 唯一
                    options = ["尚未決定"] + [f"{ts} ({len(current_availability.get(ts, []))}人可)" for ts in valid_proposed_times]
                    current_final = schedule_to_display.get("final_time", "")
                    current_idx = 0
                    if current_final:
                        try:
                            # 找到符合前綴的選項索引
                            current_idx = next(i for i, opt in enumerate(options) if opt.startswith(current_final))
                        except StopIteration:
                            # 如果找不到（例如時間被隊長改掉），則預設為 "尚未決定"
                            current_idx = 0

                    selected_str = st.selectbox("隊長確認時間", options=options, index=current_idx, key=f"final_time_{idx}_{view_week_start_str}")

                    if st.form_submit_button("✅ 確認最終時間", use_container_width=True):
                        final_time_to_save = ""
                        if selected_str != "尚未決定":
                            match = re.match(r"^(.*?)\s*\(\d+人可\)$", selected_str)
                            if match:
                                final_time_to_save = match.group(1).strip()
                        st.session_state.data["teams"][idx]["schedules"][view_week_start_str]["final_time"] = final_time_to_save
                        sync_data_and_save()
                        st.success(f"最終時間已確認為：{final_time_to_save or '尚未決定'}")
                        st.rerun()

st.header("➕ 建立新隊伍")
with st.form("add_team_form", clear_on_submit=True):
    new_team_name_input = st.text_input("新隊伍名稱", placeholder=f"例如：拉圖斯 {len(teams) + 1} 隊")
    if st.form_submit_button("建立隊伍"):
        if new_team_name_input:
            new_schedules = {
                start_of_this_week_str: get_default_schedule_for_week(),
                start_of_next_week_str: get_default_schedule_for_week()
            }
            # 建立隊伍時，預設給予空的 proposed_slots，讓隊長可以直接填寫
            new_schedules[start_of_this_week_str]['proposed_slots'] = {day: "" for day in generate_weekly_schedule_days(start_of_this_week)}
            new_schedules[start_of_next_week_str]['proposed_slots'] = {day: "" for day in generate_weekly_schedule_days(start_of_this_week + timedelta(days=7))}


            st.session_state.data.setdefault("teams", []).append({
                "team_name": new_team_name_input,
                "team_remark": "",
                "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)],
                "schedules": new_schedules
            })
            sync_data_and_save()
            st.success(f"已成功建立新隊伍：{new_team_name_input}！")
            st.rerun()
        else:
            st.warning("請輸入隊伍名稱！")
