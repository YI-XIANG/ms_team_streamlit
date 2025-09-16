import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import re
from typing import Tuple

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, db as firebase_db

MAX_TEAM_SIZE = 6
UNAVAILABLE_KEY = "__UNAVAILABLE__"


def _parse_firebase_url(full_url: str) -> Tuple[str, str]:
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
    if not firebase_admin._apps:
        service_account_info = dict(st.secrets["gcp_service_account"])  # from secrets.toml / cloud secrets
        database_url_full = st.secrets["firebase"]["url"]
        database_url_base, _ = _parse_firebase_url(database_url_full)
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            "databaseURL": database_url_base
        })


def _get_rtdb_ref():
    _init_firebase_admin_if_needed()
    database_url_full = st.secrets["firebase"]["url"]
    _, ref_path = _parse_firebase_url(database_url_full)
    return firebase_db.reference(ref_path)


def get_start_of_week(base_date: date) -> date:
    days_since_thu = (base_date.weekday() - 3) % 7
    return base_date - timedelta(days=days_since_thu)


def get_default_schedule_for_week():
    return {
        "proposed_slots": {},
        "availability": {UNAVAILABLE_KEY: []},
        "final_time": "",
    }


def load_data():
    try:
        ref = _get_rtdb_ref()
        data = ref.get() or {"teams": [], "members": {}}
        data.setdefault("teams", [])
        data.setdefault("members", {})
        return data
    except Exception as e:
        st.error(f"❌ 載入資料時發生未預期的錯誤：{e}")
        return {"teams": [], "members": {}}


def save_data(data):
    try:
        ref = _get_rtdb_ref()
        ref.set(data)
    except Exception as e:
        st.error(f"❌ 儲存資料時發生未預期的錯誤：{e}")


def build_team_text(team):
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
    start_of_week = get_start_of_week(base_date)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%m/%d')} ~ {end_of_week.strftime('%m/%d')}"


def generate_weekly_schedule_days(start_date: date) -> list[str]:
    start_of_week = get_start_of_week(start_date)
    weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
    schedule_days = [
        f"星期{weekdays_zh[(start_of_week + timedelta(days=i)).weekday()]} ({(start_of_week + timedelta(days=i)).strftime('%m-%d')})"
        for i in range(7)
    ]
    return schedule_days


st.title("📋 手動分隊")

data = load_data()
teams = data.get("teams", [])
all_members = data.get("members", {})
member_names_for_team_select = [""] + sorted(list(all_members.keys()))

today = date.today()
start_of_this_week = get_start_of_week(today)
start_of_this_week_str = start_of_this_week.strftime('%Y-%m-%d')
start_of_next_week_str = (start_of_this_week + timedelta(days=7)).strftime('%Y-%m-%d')

team_view_week = {}

for idx, team in enumerate(teams):
    if "team_view_week" not in st.session_state:
        st.session_state.team_view_week = {}
    if idx not in st.session_state.team_view_week:
        st.session_state.team_view_week[idx] = start_of_this_week_str

    view_week_start_str = st.session_state.team_view_week[idx]
    view_week_start_date = datetime.strptime(view_week_start_str, '%Y-%m-%d').date()

    schedule_to_display = team.get("schedules", {}).get(view_week_start_str, get_default_schedule_for_week())
    final_time = schedule_to_display.get('final_time')

    expander_label = f"🍁 **{team['team_name']}**｜📅 **最終時間：{final_time}**" if final_time else f"🍁 **{team['team_name']}**"
    with st.expander(expander_label):
        member_count = sum(1 for m in team.get("member", []) if m.get("name"))
        c1, c2 = st.columns([3, 1])
        c1.progress(member_count / MAX_TEAM_SIZE, text=f"👥 人數: {member_count} / {MAX_TEAM_SIZE}")
        c2.info(f"✨ 尚缺 {MAX_TEAM_SIZE - member_count} 人" if member_count < MAX_TEAM_SIZE else "🎉 人數已滿")
        st.markdown("---")

        tab1, = st.tabs(["**👥 成員名單**"])

        with tab1:
            # 週次切換（本週 / 下週），影響下方 DataFrame 的日期欄位與可參加勾選來源
            view_choice = st.radio("顯示週次", ["本週", "下週"], horizontal=True, key=f"member_list_week_{idx}")
            week_start_date = start_of_this_week if view_choice == "本週" else (start_of_this_week + timedelta(days=7))
            week_key_str = week_start_date.strftime('%Y-%m-%d')
            weekday_plain = ["星期四", "星期五", "星期六", "星期日", "星期一", "星期二", "星期三"]
            weekday_with_date = [
                f"星期四({(week_start_date + timedelta(days=0)).strftime('%m/%d')})",
                f"星期五({(week_start_date + timedelta(days=1)).strftime('%m/%d')})",
                f"星期六({(week_start_date + timedelta(days=2)).strftime('%m/%d')})",
                f"星期日({(week_start_date + timedelta(days=3)).strftime('%m/%d')})",
                f"星期一({(week_start_date + timedelta(days=4)).strftime('%m/%d')})",
                f"星期二({(week_start_date + timedelta(days=5)).strftime('%m/%d')})",
                f"星期三({(week_start_date + timedelta(days=6)).strftime('%m/%d')})",
            ]
            with st.form(f"team_form_{idx}", clear_on_submit=False):
                c1, c2 = st.columns(2)
                team_name = c1.text_input("隊伍名稱", value=team["team_name"], key=f"name_{idx}")
                team_remark = c2.text_input("隊伍備註", value=team.get("team_remark", ""), key=f"remark_{idx}", help="主要時間請至「時間調查」分頁設定")
                st.write("**編輯隊伍成員 (請由名稱欄位選擇)：**")

                current_members_list = team.get("member", [])
                if len(current_members_list) != MAX_TEAM_SIZE:
                    current_members_list.extend([{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE - len(current_members_list))])
                current_members_list = current_members_list[:MAX_TEAM_SIZE]

                # 合併為單一 DataFrame，並加入上方欄位與可參加日期（依週次切換）
                member_names_for_team_select = [""] + sorted(list(all_members.keys()))
                rows = []
                for m in current_members_list:
                    nm = m.get("name", "")
                    base_info = all_members.get(nm, {}) if nm in all_members else {}
                    job = base_info.get("job", m.get("job", ""))
                    level = base_info.get("level", m.get("level", ""))
                    atk = base_info.get("atk", m.get("atk", ""))
                    # 取所選週次的 availability（優先 weekly_data，其次舊欄位在同週）
                    weekly_data = base_info.get("weekly_data", {}) if isinstance(base_info.get("weekly_data", {}), dict) else {}
                    if week_key_str in weekly_data:
                        wa = weekly_data.get(week_key_str, {}).get("availability", {}) or {}
                    elif base_info.get("weekly_week_start") == week_key_str:
                        wa = base_info.get("weekly_availability", {}) or {}
                    else:
                        wa = {}
                    row = {"名稱": nm, "職業": job, "等級": level, "表攻": atk}
                    for p, w in zip(weekday_plain, weekday_with_date):
                        row[w] = "✅" if wa.get(p, False) else ""
                    rows.append(row)
                if rows:
                    df_combined = pd.DataFrame(rows, columns=["名稱","職業","等級","表攻"] + weekday_with_date)
                else:
                    df_combined = pd.DataFrame(columns=["名稱","職業","等級","表攻"] + weekday_with_date)

                edited_df = st.data_editor(df_combined, key=f"editor_{idx}", num_rows="fixed", use_container_width=True,
                    column_config={
                        "_index": None,
                        "名稱": st.column_config.SelectboxColumn("名稱", options=member_names_for_team_select, required=False),
                        "職業": st.column_config.TextColumn("職業", disabled=True),
                        "等級": st.column_config.TextColumn("等級", disabled=True),
                        "表攻": st.column_config.TextColumn("表攻", disabled=True),
                        **{label: st.column_config.TextColumn(label, disabled=True) for label in weekday_with_date},
                    },
                    column_order=("名稱", "職業", "等級", "表攻", *weekday_with_date)
                )
                st.markdown("---")

                btn_cols = st.columns([2, 1, 1, 2])
                if btn_cols[0].form_submit_button(f"💾 儲存變更", type="primary", use_container_width=True):
                    updated_members = [
                        {"name": row["名稱"], **all_members.get(row["名稱"], {})} if row["名稱"] else {"name": "", "job": "", "level": "", "atk": ""}
                        for _, row in edited_df.iterrows()
                    ]
                    data["teams"][idx].update({
                        "team_name": team_name,
                        "team_remark": team_remark,
                        "member": updated_members
                    })
                    save_data(data)
                    st.success(f"隊伍 '{team_name}' 的資料已更新！")
                    st.rerun()

                if btn_cols[1].form_submit_button(f"🔄 清空成員", use_container_width=True):
                    data["teams"][idx]["member"] = [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)]
                    save_data(data)
                    st.success(f"隊伍 '{team['team_name']}' 的成員已清空！")
                    st.rerun()

                if btn_cols[2].form_submit_button(f"🗑️ 刪除隊伍", use_container_width=True):
                    deleted_name = data["teams"].pop(idx)["team_name"]
                    save_data(data)
                    st.success(f"隊伍 '{deleted_name}' 已被刪除！")
                    st.rerun()


        # 移除「時間調查」頁籤與相關功能

st.header("➕ 建立新隊伍")
with st.form("add_team_form", clear_on_submit=True):
    new_team_name_input = st.text_input("新隊伍名稱")
    if st.form_submit_button("建立隊伍"):
        if new_team_name_input:
            new_schedules = {
                start_of_this_week_str: get_default_schedule_for_week(),
                start_of_next_week_str: get_default_schedule_for_week()
            }
            new_schedules[start_of_this_week_str]['proposed_slots'] = {day: "" for day in generate_weekly_schedule_days(start_of_this_week)}
            new_schedules[start_of_next_week_str]['proposed_slots'] = {day: "" for day in generate_weekly_schedule_days(start_of_this_week + timedelta(days=7))}

            data.setdefault("teams", []).append({
                "team_name": new_team_name_input,
                "team_remark": "",
                "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)],
                "schedules": new_schedules
            })
            save_data(data)
            st.success(f"已成功建立新隊伍：{new_team_name_input}！")
        else:
            st.warning("請輸入隊伍名稱！")


