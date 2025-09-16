import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
<<<<<<< HEAD
import re
import json
import io
from typing import Tuple

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, db as firebase_db

=======
import requests
import re
import json
import io

>>>>>>> ae27d7fb0771bb0127058d95f8f1759302e40175
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

<<<<<<< HEAD
def _parse_firebase_url(full_url: str) -> Tuple[str, str]:
    """將 secrets 中的完整 RTDB URL 拆成 databaseURL 與 reference path。
    例如: https://example-default-rtdb.firebaseio.com/team_info ->
      (https://example-default-rtdb.firebaseio.com, /team_info)
    """
    if not full_url:
        raise ValueError("firebase.url is empty in secrets")
    url = full_url.strip()
    if url.endswith(".json"):
        url = url[:-5]
    url = url.rstrip("/")

    marker = ".com"
    idx = url.find(marker)
    if idx == -1:
        raise ValueError("Invalid Firebase RTDB URL: missing '.com'")
    base = url[: idx + len(marker)]
    path = url[idx + len(marker) :]
    path = path if path else "/"
    if not path.startswith("/"):
        path = "/" + path
    return base, path

def _init_firebase_admin_if_needed():
    """使用 Service Account 初始化 Firebase Admin（僅初始化一次）。"""
    if not firebase_admin._apps:
        service_account_info = dict(st.secrets["gcp_service_account"])  # from secrets.toml / cloud secrets
        database_url_full = st.secrets["firebase"]["url"]
        database_url_base, _ = _parse_firebase_url(database_url_full)
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            "databaseURL": database_url_base
        })

def _get_rtdb_ref():
    """回傳專案資料的 RTDB 參照。"""
    _init_firebase_admin_if_needed()
    database_url_full = st.secrets["firebase"]["url"]
    _, ref_path = _parse_firebase_url(database_url_full)
    return firebase_db.reference(ref_path)

def get_start_of_week(base_date: date) -> date:
    """計算給定日期所在週的星期四是哪一天。
    若今天為星期一，為符合需求自動跳至下一週的星期四（本週9/11 -> 9/18 的情況）。
    """
    days_since_thu = (base_date.weekday() - 3) % 7
    start = base_date - timedelta(days=days_since_thu)
    # 若今天是星期一，跳至下週的星期四
    if base_date.weekday() == 0:  # Monday
        start = start + timedelta(days=7)
    return start
=======
def get_start_of_week(base_date: date) -> date:
    """計算給定日期所在週的星期四是哪一天"""
    days_since_thu = (base_date.weekday() - 3) % 7
    return base_date - timedelta(days=days_since_thu)
>>>>>>> ae27d7fb0771bb0127058d95f8f1759302e40175

def get_default_schedule_for_week():
    """回傳一週行程的預設資料結構"""
    return {
        "proposed_slots": {},
        "availability": {UNAVAILABLE_KEY: []},
        "final_time": "",
    }

def load_data():
<<<<<<< HEAD
    """從 Firebase 載入、遷移並驗證資料結構（使用 Admin SDK）。"""
    try:
        ref = _get_rtdb_ref()
        data = ref.get()
=======
    """從 Firebase 載入、遷移並驗證資料結構"""
    firebase_url = st.secrets["firebase"]["url"]
    try:
        response = requests.get(f"{firebase_url}.json")
        response.raise_for_status()
        data = response.json()
>>>>>>> ae27d7fb0771bb0127058d95f8f1759302e40175

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

<<<<<<< HEAD
=======
    except requests.exceptions.RequestException as e:
        st.error(f"❌ 無法從 Firebase 載入資料，網路錯誤：{e}")
>>>>>>> ae27d7fb0771bb0127058d95f8f1759302e40175
    except Exception as e:
        st.error(f"❌ 載入資料時發生未預期的錯誤：{e}, {e.__traceback__.tb_lineno}")

    return {"teams": [], "members": {}}

def save_data(data):
<<<<<<< HEAD
    """將資料儲存到 Firebase（使用 Admin SDK）。"""
    try:
        ref = _get_rtdb_ref()
        # 直接 set Python 物件，Admin SDK 會處理序列化
        ref.set(data)
    except Exception as e:
        st.error(f"❌ 儲存資料時發生未預期的錯誤：{e}")

def reset_weekly_availability_if_monday(data: dict) -> dict:
    """每週一清空所有成員的 weekly_availability，並以日期標記避免重複執行。"""
    try:
        today_date = date.today()
        if today_date.weekday() != 0:  # 0 = Monday
            return data
        today_str = today_date.strftime('%Y-%m-%d')
        if data.get("weekly_reset_marker") == today_str:
            return data
        for _, info in data.get("members", {}).items():
            info["weekly_availability"] = {}
            info["weekly_last_updated"] = ""
            info["weekly_week_start"] = get_start_of_week(today_date).strftime('%Y-%m-%d')
        data["weekly_reset_marker"] = today_str
        save_data(data)
    except Exception:
        pass
    return data

=======
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

>>>>>>> ae27d7fb0771bb0127058d95f8f1759302e40175
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

<<<<<<< HEAD
def render_global_weekly_availability():
    """Render 本週與下週可參加名單（唯讀）。"""
    st.markdown("---")
    st.subheader("全局：本週與下週可參加名單（唯讀）")
    week_view = st.radio("檢視週次", ["本週", "下週"], horizontal=True)
    today = date.today()
    start_this = get_start_of_week(today)
    week_start = start_this if week_view == "本週" else start_this + timedelta(days=7)
    week_days = generate_weekly_schedule_days(week_start)

    rows = []
    for name, info in st.session_state.data.get("members", {}).items():
        wa = info.get("weekly_availability", {})
        # 只顯示在該週內有填寫的成員資訊
        if not any(wa.get(d, False) for d in week_days):
            continue
        row = {"名稱": name, "職業": info.get("job", ""), "等級": info.get("level", "")}
        mapping = {
            week_days[0]: "星期四",
            week_days[1]: "星期五",
            week_days[2]: "星期六",
            week_days[3]: "星期日",
            week_days[4]: "星期一",
            week_days[5]: "星期二",
            week_days[6]: "星期三",
        }
        for label in week_days:
            wk = mapping[label]
            row[label] = "✅" if wa.get(wk, False) else ""
        rows.append(row)
    df_week = pd.DataFrame(rows, columns=["名稱","職業","等級"] + week_days)
    if not df_week.empty:
        st.dataframe(df_week, use_container_width=True)
    else:
        st.info("本週尚無成員勾選可參加日期。")
    return

=======
>>>>>>> ae27d7fb0771bb0127058d95f8f1759302e40175
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

@st.dialog("下載人員手冊")
def download_members_csv():
    """彈跳視窗：輸入密碼下載人員手冊"""
    st.write("請輸入管理員密碼以下載完整人員手冊：")
    
    password = st.text_input("密碼", type="password", key="download_password")
    
    col1, col2 = st.columns(2)
    
    if col1.button("下載", type="primary", use_container_width=True):
        # 這裡可以自訂密碼，建議從 secrets 讀取
        correct_password = st.secrets.get("download_password", st.secrets["setting"]["pwd"])
        
        if password == correct_password:
            # 準備 CSV 資料
            all_members = st.session_state.data.get("members", {})
            if all_members:
                members_data = []
                for name, info in all_members.items():
                    members_data.append({
                        "遊戲ID": name,
                        "職業": info.get("job", ""),
                        "等級": info.get("level", ""),
                        "表攻": info.get("atk", ""),
                        "公會成員": "是" if info.get("is_guild_member", True) else "否"
                    })
                
                df = pd.DataFrame(members_data)
                
                # 轉換為 CSV
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                csv_data = csv_buffer.getvalue()
                
                # 產生檔案名稱
                current_date = datetime.now().strftime("%Y%m%d")
                filename = f"楓之谷公會成員名冊_{current_date}.csv"
                
                st.download_button(
                    label="📥 下載 CSV 檔案",
                    data=csv_data,
                    file_name=filename,
                    mime="text/csv",
                    use_container_width=True
                )
                st.success("密碼正確！請點擊上方按鈕下載檔案。")
            else:
                st.warning("目前沒有成員資料可供下載。")
        else:
            st.error("密碼錯誤，請重新輸入。")
    
    if col2.button("取消", use_container_width=True):
        st.rerun()


# --- 初始化 Session State & 同步函式 ---
if "data" not in st.session_state:
    st.session_state.data = load_data()
    st.session_state.data = reset_weekly_availability_if_monday(st.session_state.data)

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

# ------ 註冊功能 ------
st.header("👤 公會成員表")
<<<<<<< HEAD
if "profile_expander_open" not in st.session_state:
    st.session_state.profile_expander_open = True
with st.expander("點此註冊或更新你的個人資料", expanded=st.session_state.profile_expander_open):
    all_members = st.session_state.data.get("members", {})

    # 週次切換 與 次數：放在表單外同一列，切換時可即時重繪日期勾選
    ctrl_col1, ctrl_col2 = st.columns([3, 1])
    # 週次切換
    today_date = date.today()
    start_this_thu = get_start_of_week(today_date)
    start_next_thu = start_this_thu + timedelta(days=7)
    week_choice = ctrl_col1.radio("填寫週次", ["本週", "下週"], horizontal=True, key="member_week_choice")
    start_thu_external = start_this_thu if week_choice == "本週" else start_next_thu
    # 次數預設（沿用該會員最近填寫的數值），依目前已選的 ID（若尚未選擇則使用 1）
    week_key_external = start_thu_external.strftime('%Y-%m-%d')
    current_input_id = st.session_state.get("member_id_input_main")
    if current_input_id and current_input_id in all_members:
        _info = all_members.get(current_input_id, {})
        _wdata = _info.get("weekly_data", {}) if isinstance(_info.get("weekly_data", {}), dict) else {}
        if str(_wdata.get(week_key_external, {}).get("participation_count", "")).isdigit():
            participation_count_default = int(_wdata.get(week_key_external, {}).get("participation_count", 1))
        elif str(_info.get("weekly_participation_count", "")).isdigit():
            participation_count_default = int(_info.get("weekly_participation_count", 1))
        else:
            participation_count_default = 1
    else:
        participation_count_default = 1
    participation_count_input = ctrl_col2.selectbox("次數", options=[1, 2], index=[1,2].index(participation_count_default), key="member_participation_count", help="參與次數（依週次紀錄）")

    # 選單選擇既有ID後自動帶入到輸入框（放在表單外，避免 on_change 限制）
    def _on_pick_existing_member():
        picked = st.session_state.get("member_id_select_existing", "")
        if picked and picked != "<創建成員>":
            st.session_state["member_id_input_main"] = picked
        else:
            # 進入新建模式：清空欄位與次數
            st.session_state["member_id_input_main"] = ""
            st.session_state["member_participation_count"] = 1
        st.session_state.profile_expander_open = True

    member_options = sorted(list(all_members.keys()))
    st.selectbox(
        "從名單選擇（將自動帶入下方輸入框）",
        options=["<創建成員>"] + member_options,
        key="member_id_select_existing",
        on_change=_on_pick_existing_member,
    )

    with st.form("member_form", clear_on_submit=False):
        c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 1, 1, 1, 1])
        # 遊戲ID：選到既有成員時不可編輯；創建模式可輸入
        member_id_input = c1.text_input("遊戲ID", key="member_id_input_main", disabled=st.session_state.get("member_id_input_main", "") in all_members)
        selected_member_name = member_id_input if member_id_input in all_members else ""
        default_info = all_members.get(selected_member_name, {"job": "", "level": "", "atk": "", "is_guild_member": True})
        job_index = JOB_SELECT_LIST.index(default_info.get("job", "")) if default_info.get("job") in JOB_SELECT_LIST else 0
        is_existing = bool(selected_member_name)
        job_input = c2.selectbox("職業", options=JOB_SELECT_LIST, index=job_index, disabled=False)
        level_input = c3.text_input("等級", value=default_info.get("level", ""))
        atk_input = c4.text_input("表攻 (乾表)", value=default_info.get("atk", ""))
        is_guild_member = c5.checkbox("公會成員", value=default_info.get("is_guild_member", True), help="勾選表示為公會正式成員")
        # c6 位置保留，不再重複顯示「次數」

        st.markdown("---")
        # 每週可參加日期（週四 -> 下週三），依表單外週次切換連動
        start_thu = start_thu_external
        day_names = ["星期四", "星期五", "星期六", "星期日", "星期一", "星期二", "星期三"]
        days = [(start_thu + timedelta(days=i), day_names[i]) for i in range(7)]
        cols = st.columns(7)
        # 僅在同一週次時才預填上次資料（優先從 weekly_data 取）
        week_key = start_thu.strftime('%Y-%m-%d')
        # 依當前選擇的成員，抓取該成員於該週的預設
        weekly_data_default = default_info.get("weekly_data", {}) if isinstance(default_info.get("weekly_data", {}), dict) else {}
        weekly_default = {}
        if week_key in weekly_data_default:
            weekly_default = weekly_data_default.get(week_key, {}).get("availability", {}) or {}
        elif default_info.get("weekly_week_start") == week_key:
            weekly_default = default_info.get("weekly_availability", {}) or {}
        weekly_availability = {}
        for i, (d, label) in enumerate(days):
            weekly_availability[label] = cols[i].checkbox(f"{label}\n{d.strftime('%m/%d')}", value=bool(weekly_default.get(label, False)))

        button_cols = st.columns([3, 1, 1, 1])
        if button_cols[0].form_submit_button("💾 儲存角色資料", use_container_width=True):
            final_name = (member_id_input or "").strip()
            if not final_name:
                st.warning("請務必填寫遊戲ID！")
            else:
                member_dict = st.session_state.data.setdefault("members", {}).get(final_name, {})
                now_iso = datetime.now().isoformat(timespec="seconds")
                week_key = start_thu.strftime('%Y-%m-%d')
                # 儲存基本資料
                member_dict.update({
                    "job": job_input,
                    "level": level_input,
                    "atk": atk_input,
                    "is_guild_member": is_guild_member,
                })
                # 新結構：依週次儲存
                weekly_data = member_dict.setdefault("weekly_data", {})
                weekly_data[week_key] = {
                    "availability": weekly_availability,
                    "participation_count": st.session_state.get("member_participation_count", 1),
                    "last_updated": now_iso,
                }
                # 舊欄位（相容既有頁面）：同步為當前週次資料
                member_dict.update({
                    "weekly_availability": weekly_availability,
                    "weekly_last_updated": now_iso,
                    "weekly_week_start": week_key,
                    "weekly_participation_count": st.session_state.get("member_participation_count", 1),
                })
                # 寫回成員
                st.session_state.data["members"][final_name] = member_dict
                sync_data_and_save()
                st.success(f"角色 '{final_name}' 的資料已儲存！")
                st.session_state.profile_expander_open = True
                st.rerun()

        if selected_member_name and button_cols[1].form_submit_button("🗑️ 刪除此角色", use_container_width=True):
            del st.session_state.data["members"][selected_member_name]
            # 同步刪除隊伍中的成員
            for team_idx in range(len(st.session_state.data['teams'])):
                st.session_state.data['teams'][team_idx]['member'] = [
                    m for m in st.session_state.data['teams'][team_idx].get('member', []) if m.get('name') != selected_member_name
                ]
            sync_data_and_save()
            st.success(f"角色 '{selected_member_name}' 已從名冊中刪除！")
            st.session_state.profile_expander_open = True
            st.rerun()

    # 下載功能放在表單外面
    st.markdown("---")
    if st.button("📥 下載人員手冊", type="secondary", help="需要管理員密碼"):
        download_members_csv()

    # 全局顯示移至下方統一區塊

st.subheader("已報名成員（可切換本週/下週）")
list_week_choice = st.radio("顯示週次", ["本週", "下週"], horizontal=True, key="list_week_choice")
today = date.today()
start_this = get_start_of_week(today)
week_start = start_this if list_week_choice == "本週" else start_this + timedelta(days=7)
weekday_labels = [
    f"星期四({(week_start + timedelta(days=0)).strftime('%m/%d')})",
    f"星期五({(week_start + timedelta(days=1)).strftime('%m/%d')})",
    f"星期六({(week_start + timedelta(days=2)).strftime('%m/%d')})",
    f"星期日({(week_start + timedelta(days=3)).strftime('%m/%d')})",
    f"星期一({(week_start + timedelta(days=4)).strftime('%m/%d')})",
    f"星期二({(week_start + timedelta(days=5)).strftime('%m/%d')})",
    f"星期三({(week_start + timedelta(days=6)).strftime('%m/%d')})",
]
weekday_plain = ["星期四","星期五","星期六","星期日","星期一","星期二","星期三"]

rows = []
show_week = week_start.strftime('%Y-%m-%d')
for name, info in st.session_state.data.get("members", {}).items():
    # 優先從 weekly_data 讀取該週資料
    weekly_data = info.get("weekly_data", {}) if isinstance(info.get("weekly_data", {}), dict) else {}
    week_obj = weekly_data.get(show_week)
    if not week_obj:
        # 回退舊欄位（只在同週次時顯示）
        if info.get("weekly_week_start") != show_week:
            continue
        wa = info.get("weekly_availability", {}) or {}
        pc = info.get("weekly_participation_count", "")
    else:
        wa = week_obj.get("availability", {}) or {}
        pc = week_obj.get("participation_count", "")

    # 僅顯示有報名（有任一勾選）的人
    if not any(bool(wa.get(p, False)) for p in weekday_plain):
        continue

    participation_count_str = "" if pc in (None, "") else str(pc)
    row = {
        "名稱": name,
        "職業": str(info.get("job", "")),
        "等級": str(info.get("level", "")),
        "次數": participation_count_str
    }
    for plain, label in zip(weekday_plain, weekday_labels):
        row[label] = "✅" if wa.get(plain, False) else ""
    rows.append(row)

df_members = pd.DataFrame(rows, columns=["名稱","職業","等級","次數"] + weekday_labels)
st.dataframe(df_members, use_container_width=True, hide_index=True)
    
=======
with st.expander("點此註冊或更新你的個人資料"):
    all_members = st.session_state.data.get("members", {})
    member_list_for_select = [""] + sorted(list(all_members.keys()))

    selected_member_name = st.selectbox("選擇你的角色 (或留空以註冊新角色)", options=member_list_for_select, key="member_select_main")
    default_info = all_members.get(selected_member_name, {"job": "", "level": "", "atk": "", "is_guild_member": True})
    job_index = JOB_SELECT_LIST.index(default_info["job"]) if default_info.get("job") in JOB_SELECT_LIST else 0

    with st.form("member_form", clear_on_submit=False):
        c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
        name_input = c1.text_input("遊戲ID", value=selected_member_name, disabled=bool(selected_member_name), help="註冊新角色時請在此填寫ID，選擇舊角色則此欄不可編輯。")
        job_input = c2.selectbox("職業", options=JOB_SELECT_LIST, index=job_index)
        level_input = c3.text_input("等級", value=default_info.get("level", ""))
        atk_input = c4.text_input("表攻 (乾表)", value=default_info.get("atk", ""))
        is_guild_member = c5.checkbox("公會成員", value=default_info.get("is_guild_member", True), help="勾選表示為公會正式成員")

        button_cols = st.columns([3, 1, 1])
        if button_cols[0].form_submit_button("💾 儲存角色資料", use_container_width=True):
            final_name = selected_member_name or name_input.strip()
            if not final_name:
                st.warning("請務必填寫遊戲ID！")
            else:
                st.session_state.data["members"][final_name] = {
                    "job": job_input, 
                    "level": level_input, 
                    "atk": atk_input,
                    "is_guild_member": is_guild_member
                }
                sync_data_and_save()
                st.success(f"角色 '{final_name}' 的資料已儲存！")
                st.rerun()

        if selected_member_name and button_cols[1].form_submit_button("🗑️ 刪除此角色", use_container_width=True):
            del st.session_state.data["members"][selected_member_name]
            # 同步刪除隊伍中的成員
            for team_idx in range(len(st.session_state.data['teams'])):
                st.session_state.data['teams'][team_idx]['member'] = [
                    m for m in st.session_state.data['teams'][team_idx].get('member', []) if m.get('name') != selected_member_name
                ]
            sync_data_and_save()
            st.success(f"角色 '{selected_member_name}' 已從名冊中刪除！")
            st.rerun()

    # 下載功能放在表單外面
    st.markdown("---")
    if st.button("📥 下載人員手冊", type="secondary", help="需要管理員密碼"):
        download_members_csv()

# ------ 組隊功能 ------
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
>>>>>>> ae27d7fb0771bb0127058d95f8f1759302e40175
