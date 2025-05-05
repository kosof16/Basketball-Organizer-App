import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time, timedelta
import random
import altair as alt
import time as t
import io

# --- Constants ---
CAPACITY = 15
DEFAULT_LOCATION = "Main Court"
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
CUTOFF_DAYS = 2  # RSVP closes 2 days before game

# --- Page Config ---
st.set_page_config(page_title="🏀 Basketball Organiser", layout="wide")

# --- Session State ---
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

st.sidebar.markdown("# 📜 Menu")
section = st.sidebar.selectbox("Navigate to", ["🏀 RSVP", "⚙️ Admin"])

# --- File Paths ---
def _paths(backend):
    return ('game.csv' if backend == 'csv' else 'game.xlsx',
            'responses.csv' if backend == 'csv' else 'responses.xlsx')

def load_game(backend):
    game_path, _ = _paths(backend)
    if os.path.exists(game_path):
        return pd.read_csv(game_path) if backend == 'csv' else pd.read_excel(game_path)
    return pd.DataFrame()

def save_game(backend, date_str, start_str, end_str, location):
    df = pd.DataFrame([{'date': date_str, 'start': start_str, 'end': end_str, 'location': location}])
    game_path, _ = _paths(backend)
    df.to_csv(game_path, index=False) if backend == 'csv' else df.to_excel(game_path, index=False)

def load_responses(backend):
    _, resp_path = _paths(backend)
    if os.path.exists(resp_path):
        return pd.read_csv(resp_path) if backend == 'csv' else pd.read_excel(resp_path)
    return pd.DataFrame(columns=['name', 'others', 'timestamp', 'status'])

def save_responses(df, backend):
    _, resp_path = _paths(backend)
    df.to_csv(resp_path, index=False) if backend == 'csv' else df.to_excel(resp_path, index=False)

# --- Utilities ---
def format_time_str(t_str):
    try:
        t = datetime.fromisoformat(t_str).time()
    except:
        parts = t_str.split(':')
        t = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    h, m = t.hour, t.minute
    ampm = 'am' if h < 12 else 'pm'
    hr = h % 12 or 12
    if h == 12 and m == 0:
        return '12 noon'
    if m == 0:
        return f"{hr} {ampm}"
    return f"{hr}:{m:02d} {ampm}"

def add_response(backend, name, others, attend):
    df = load_responses(backend)
    df = df[df['name'] != name]
    status = '❌ Cancelled' if not attend else ''
    entry = {'name': name, 'others': others, 'timestamp': datetime.utcnow().isoformat(), 'status': status}
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    save_responses(df, backend)

def update_statuses(backend):
    df = load_responses(backend).sort_values('timestamp')
    cum = 0
    statuses = []
    for _, r in df.iterrows():
        current_status = r['status']
        if current_status in ['❌ Cancelled', '✅ Confirmed', '⏳ Waitlist']:
            statuses.append(current_status)  # Preserve manual edits
        else:
            others = str(r.get('others', '') or '')
            extras = len([o for o in others.split(',') if o.strip()])
            parts = 1 + extras
            if cum + parts <= CAPACITY:
                statuses.append('✅ Confirmed')
                cum += parts
            else:
                statuses.append('⏳ Waitlist')
    df['status'] = statuses
    save_responses(df, backend)

def generate_teams(backend, num_teams=None):
    update_statuses(backend)
    df = load_responses(backend)
    confirmed = df[df['status'] == '✅ Confirmed']
    players = []
    for _, r in confirmed.iterrows():
        players.append(r['name'])
        others = str(r.get('others', '') or '')
        for o in others.split(','):
            if o.strip(): players.append(o.strip())
    if len(players) < 2:
        return None
    if not num_teams:
        num_teams = 2 if len(players) <= 10 else (len(players) + 2) // 3
    num_teams = max(2, min(num_teams, len(players)))
    random.shuffle(players)
    teams = [[] for _ in range(num_teams)]
    for i, p in enumerate(players):
        teams[i % num_teams].append(p)
    return teams

def show_metrics_and_chart(df):
    conf = len(df[df['status'] == '✅ Confirmed'])
    wait = len(df[df['status'] == '⏳ Waitlist'])
    canc = len(df[df['status'] == '❌ Cancelled'])
    col1, col2, col3 = st.columns(3)
    col1.metric("✅ Confirmed", conf)
    col2.metric("⏳ Waitlist", wait)
    col3.metric("❌ Cancelled", canc)
    st.progress(min(conf / CAPACITY, 1.0), text=f"{conf}/{CAPACITY} confirmed")
    chart_data = pd.DataFrame({'Status': ['Confirmed', 'Waitlist', 'Cancelled'],
                               'Count': [conf, wait, canc]})
    color_map = {'Confirmed': '#4CAF50', 'Waitlist': '#FFC107', 'Cancelled': '#F44336'}
    chart = alt.Chart(chart_data).mark_bar().encode(
        y=alt.Y('Status:N', sort='-x', title=''),
        x=alt.X('Count:Q', title='Players'),
        color=alt.Color('Status:N', scale=alt.Scale(domain=list(color_map.keys()), range=list(color_map.values()))),
        tooltip=['Status:N', 'Count:Q']
    ).properties(width=500, height=200)
    st.altair_chart(chart, use_container_width=True)

def show_admin_table(df, backend, status_filter):
    filtered = df[df['status'] == status_filter][['name', 'others']].reset_index(drop=True)
    if filtered.empty:
        st.info(f"No {status_filter} players.")
        return
    selected = st.multiselect(f"Select {status_filter} players to modify:", filtered['name'].tolist())
    st.table(filtered)
    c1, c2, c3 = st.columns(3)
    if c1.button(f"Move to Confirmed from {status_filter}"):
        df.loc[df['name'].isin(selected), 'status'] = '✅ Confirmed'
        save_responses(df, backend)
        if status_filter == '❌ Cancelled':
            update_statuses(backend)
            st.toast("Capacity recalculated after restoring cancelled player.")
        st.success("Moved to Confirmed.")
        st.rerun()
    if c2.button(f"Move to Waitlist from {status_filter}"):
        df.loc[df['name'].isin(selected), 'status'] = '⏳ Waitlist'
        save_responses(df, backend)
        st.success("Moved to Waitlist.")
        st.rerun()
    if c3.button(f"Undo / Reset from {status_filter}"):
        df.loc[df['name'].isin(selected), 'status'] = ''
        save_responses(df, backend)
        update_statuses(backend)
        st.success("Status reset.")
        st.rerun()

# --- ADMIN PAGE ---
if section == '⚙️ Admin':
    st.title(":gear: Admin Dashboard")
    if not st.session_state.admin_authenticated:
        st.sidebar.markdown("## Admin Login 🔒")
        pwd = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.sidebar.error("Incorrect password")
    else:
        BACKEND = st.sidebar.selectbox("Data Backend", ['csv', 'excel'])
        game_df = load_game(BACKEND)
        st.subheader(":calendar: Schedule Game")
        with st.form("schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                gd = st.date_input("Game Date", date.today() + timedelta(days=1))
                start = st.time_input("Start Time", value=time(10))
            with col2:
                end = st.time_input("End Time", value=time(12))
                loc = st.text_input("Location", DEFAULT_LOCATION)
            if st.form_submit_button("Save Schedule"):
                save_game(BACKEND, gd.isoformat(), start.isoformat(), end.isoformat(), loc)
                st.success("Schedule saved!")

        if not game_df.empty:
            game = game_df.iloc[0].to_dict()
            st.markdown(f"**Date:** {game['date']} — **{format_time_str(game['start'])} to {format_time_str(game['end'])}** @ **{game['location']}**")

        st.subheader(":clipboard: RSVP Overview")
        df = load_responses(BACKEND)
        show_metrics_and_chart(df)

        st.subheader("✅ Confirmed Players")
        show_admin_table(df, BACKEND, '✅ Confirmed')
        st.subheader("⏳ Waitlist Players")
        show_admin_table(df, BACKEND, '⏳ Waitlist')
        st.subheader("❌ Cancelled Players")
        show_admin_table(df, BACKEND, '❌ Cancelled')

        st.subheader("📥 Download RSVP List (all statuses)")
        csv = df.to_csv(index=False).encode('utf-8')
        excel = None
        if BACKEND == 'excel':
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer) as writer:
                df.to_excel(writer, index=False)
            excel = buffer.getvalue()
        col1, col2 = st.columns(2)
        col1.download_button("Download All CSV", csv, "responses.csv", "text/csv")
        if excel:
            col2.download_button("Download All Excel", excel, "responses.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.subheader("📥 Download Individual Status Lists")
        confirmed_df = df[df['status'] == '✅ Confirmed']
        waitlist_df = df[df['status'] == '⏳ Waitlist']
        cancelled_df = df[df['status'] == '❌ Cancelled']
        c1, c2, c3 = st.columns(3)
        c1.download_button("Download Confirmed CSV", confirmed_df.to_csv(index=False).encode('utf-8'), "confirmed.csv", "text/csv")
        c2.download_button("Download Waitlist CSV", waitlist_df.to_csv(index=False).encode('utf-8'), "waitlist.csv", "text/csv")
        c3.download_button("Download Cancelled CSV", cancelled_df.to_csv(index=False).encode('utf-8'), "cancelled.csv", "text/csv")

        st.subheader("👥 Generate Teams")
        conf_count = len(confirmed_df)
        suggested_teams = 2 if conf_count <= 10 else (conf_count + 2) // 3
        num_teams_input = st.number_input(f"Number of teams (default {suggested_teams})", min_value=2, max_value=conf_count, value=suggested_teams)
        if st.button("Generate Teams"):
            teams = generate_teams(BACKEND, num_teams=num_teams_input)
            if teams:
                st.success("Teams generated!")
                for i, team in enumerate(teams, 1):
                    st.markdown(f"**Team {i}:** {', '.join(team)}")
                st.toast("Teams are ready! 📋")
                st.balloons()
            else:
                st.warning("Not enough players to generate teams.")

        if st.button("🔄 Recalculate Statuses"):
            update_statuses(BACKEND)
            st.success("Statuses recalculated.")

# --- RSVP PAGE ---
else:
    st.title(":basketball: RSVP & Game Details")
    BACKEND = 'csv'
    game_df = load_game(BACKEND)
    if game_df.empty:
        st.warning("No game scheduled. Check back later!")
    else:
        game = game_df.iloc[0].to_dict()
        date_str = game['date']
        deadline = datetime.fromisoformat(date_str).date() - timedelta(days=CUTOFF_DAYS)
        today = date.today()
        st.markdown(f"### Next Game: **{date_str}** from **{format_time_str(game['start'])}** to **{format_time_str(game['end'])}** @ **{game['location']}**")
        df = load_responses(BACKEND)
        show_metrics_and_chart(df)
        if today <= deadline:
            st.info(f"RSVP open until **{deadline}** 🕒")
            with st.form("rsvp_form"):
                name = st.text_input("Your First Name")
                attend = st.select_slider("Will you attend?", ["No ❌", "Yes ✅"], value="Yes ✅")
                others = st.text_input("Additional Players (comma-separated)")
                if st.form_submit_button("Submit RSVP 🎫"):
                    if not name.strip():
                        st.error("Name is required.")
                    else:
                        add_response(BACKEND, name.strip(), others.strip(), attend == "Yes ✅")
                        update_statuses(BACKEND)
                        st.success("RSVP recorded!")
                        st.rerun()
        else:
            st.error(f"RSVP closed on {deadline}. See you next time!")
