import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time, timedelta
import random
import altair as alt
import time as t

# --- Page Configuration ---
st.set_page_config(page_title="🏀 Basketball Organizer", layout="wide")

# --- Constants ---
CAPACITY = 15
DEFAULT_LOCATION = "Main Court"
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

st.sidebar.markdown("# 📜 Menu")
section = st.sidebar.selectbox("Navigate to", ["🏀 RSVP", "⚙️ Admin"])

def _paths(backend):
    game_path = 'game.csv' if backend == 'csv' else 'game.xlsx'
    resp_path = 'responses.csv' if backend == 'csv' else 'responses.xlsx'
    return game_path, resp_path

def load_game(backend):
    game_path, _ = _paths(backend)
    if os.path.exists(game_path):
        df = pd.read_csv(game_path) if backend == 'csv' else pd.read_excel(game_path)
        if not df.empty:
            return df.iloc[0].to_dict()
    return {}

def save_game(backend, date_str, start_str, end_str, location):
    game_path, _ = _paths(backend)
    df = pd.DataFrame([{
        'date': date_str,
        'start': start_str,
        'end': end_str,
        'location': location
    }])
    if backend == 'csv':
        df.to_csv(game_path, index=False)
    else:
        df.to_excel(game_path, index=False)

def load_responses(backend):
    _, resp_path = _paths(backend)
    if os.path.exists(resp_path):
        return pd.read_csv(resp_path) if backend == 'csv' else pd.read_excel(resp_path)
    return pd.DataFrame(columns=['name', 'others', 'timestamp', 'status'])

def save_responses(df, backend):
    _, resp_path = _paths(backend)
    if backend == 'csv':
        df.to_csv(resp_path, index=False)
    else:
        df.to_excel(resp_path, index=False)

def format_time_str(t_str):
    try:
        t = datetime.fromisoformat(t_str).time()
    except Exception:
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
        if r['status'] == '❌ Cancelled':
            statuses.append('❌ Cancelled')
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

def generate_teams(backend):
    update_statuses(backend)
    df = load_responses(backend)
    confirmed = df[df['status'] == '✅ Confirmed']
    players = []
    for _, r in confirmed.iterrows():
        players.append(r['name'])
        others = str(r.get('others', '') or '')
        for o in others.split(','):
            if o.strip(): players.append(o.strip())
    if len(players) < 6:
        return None
    num_teams = 2 if len(players) <= 10 else (len(players) + 2) // 3
    random.shuffle(players)
    teams = [[] for _ in range(num_teams)]
    for i, p in enumerate(players): teams[i % num_teams].append(p)
    return teams

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
        st.subheader(":calendar: Schedule Game")
        game = load_game(BACKEND)
        with st.form("schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                gd = st.date_input("Game Date", date.today() + timedelta(days=1))
                start = st.time_input("Start Time", value=time(10, 0))
            with col2:
                end = st.time_input("End Time", value=time(12, 0))
                loc = st.text_input("Location", value=DEFAULT_LOCATION)
            if st.form_submit_button("Save Schedule"):
                save_game(BACKEND, gd.isoformat(), start.isoformat(), end.isoformat(), loc)
                st.success("Schedule saved! 🏀")
        if game:
            start_fmt = format_time_str(game.get('start', ''))
            end_fmt = format_time_str(game.get('end', ''))
            st.markdown(f"**Date:** {game.get('date', '')} — **{start_fmt} to {end_fmt}** @ **{game.get('location', '')}**")

        st.subheader(":clipboard: RSVP Overview")
        update_statuses(BACKEND)
        df = load_responses(BACKEND)
        conf = len(df[df['status'] == '✅ Confirmed'])
        wait = len(df[df['status'] == '⏳ Waitlist'])
        canc = len(df[df['status'] == '❌ Cancelled'])
        c1, c2, c3 = st.columns(3)
        c1.metric("Confirmed", conf)
        c2.metric("Waitlist", wait)
        c3.metric("Cancelled", canc)

        with st.expander("✅ Confirmed Players", expanded=True):
            confirmed_df = df[df['status'] == '✅ Confirmed'][['name', 'others']].reset_index(drop=True)
            if confirmed_df.empty:
                st.info("No confirmed players.")
            else:
                selected_names = st.multiselect(
                    "Select confirmed player(s) to modify:",
                    confirmed_df['name'].tolist()
                )
                st.table(confirmed_df)

                colx, coly, colz = st.columns(3)
                if colx.button("❌ Move to Cancelled"):
                    df.loc[df['name'].isin(selected_names), 'status'] = '❌ Cancelled'
                    save_responses(df, BACKEND)
                    st.success("Selected players moved to Cancelled.")
                    st.rerun()

                if coly.button("⏳ Move to Waitlist"):
                    df.loc[df['name'].isin(selected_names), 'status'] = '⏳ Waitlist'
                    save_responses(df, BACKEND)
                    st.success("Selected players moved to Waitlist.")
                    st.rerun()

                if colz.button("🗑️ Remove Player"):
                    df = df[~df['name'].isin(selected_names)]
                    save_responses(df, BACKEND)
                    st.success("Selected players removed.")
                    st.rerun()

        if st.button("👥 Generate Teams"):
            teams = generate_teams(BACKEND)
            if teams:
                st.success("Teams ready! 🎉")
                for i, team in enumerate(teams, 1):
                    st.markdown(f"**Team {i}:** {', '.join(team)}")
            else:
                st.warning("Not enough players to form teams 🤷‍♂️")

# --- RSVP PAGE ---
else:
    st.title(":basketball: RSVP & Game Details")
    BACKEND = 'csv'
    game = load_game(BACKEND)
    if not game:
        st.warning("No game scheduled. Check back later! 🗓️")
    else:
        date_str = game.get('date', '')
        start_fmt = format_time_str(game.get('start', ''))
        end_fmt = format_time_str(game.get('end', ''))
        loc = game.get('location', '')
        st.markdown(f"### Next Game: **{date_str}** from **{start_fmt}** to **{end_fmt}** @ **{loc}**")

        update_statuses(BACKEND)
        df = load_responses(BACKEND)
        conf = len(df[df['status'] == '✅ Confirmed'])
        wait = len(df[df['status'] == '⏳ Waitlist'])
        canc = len(df[df['status'] == '❌ Cancelled'])

        metrics_placeholder = st.empty()
        chart_placeholder = st.empty()

        with metrics_placeholder.container():
            col1, col2, col3 = st.columns(3)
            col1.metric("✅ Confirmed", conf)
            col2.metric("⏳ Waitlist", wait)
            col3.metric("❌ Cancelled", canc)
            t.sleep(0.4)

        progress = min(conf / CAPACITY, 1.0)
        st.progress(progress, text=f"{conf}/{CAPACITY} confirmed")
        t.sleep(0.4)

        chart_data = pd.DataFrame({
            'Status': ['Confirmed', 'Waitlist', 'Cancelled'],
            'Count': [conf, wait, canc]
        })
        color_map = {'Confirmed': '#4CAF50', 'Waitlist': '#FFC107', 'Cancelled': '#F44336'}

        chart = alt.Chart(chart_data).mark_bar().encode(
            y=alt.Y('Status:N', sort='-x', title=''),
            x=alt.X('Count:Q', title='Number of Players'),
            color=alt.Color('Status:N', scale=alt.Scale(domain=list(color_map.keys()), range=list(color_map.values()))),
            tooltip=['Status:N', 'Count:Q']
        ).properties(
            width=500,
            height=200,
            title="RSVP Status Overview"
        )

        with chart_placeholder.container():
            st.altair_chart(chart, use_container_width=True)

        try:
            deadline = datetime.fromisoformat(date_str).date() - timedelta(days=1)
            today = date.today()
            if today <= deadline:
                st.info(f"Voting open until **{deadline}** 🕒")
                with st.form("rsvp_form"):
                    name = st.text_input("Your First Name", help="Please enter your first name only 🏷️")
                    attend = st.select_slider("Will you attend?", options=["No ❌", "Yes ✅"], value="Yes ✅")
                    others = st.text_input("Additional Players Invite Name(s) (comma-separated) 👥")
                    if st.form_submit_button("Submit RSVP 🎫"):
                        if not name.strip():
                            st.error("Please enter your first name.")
                        else:
                            add_response(BACKEND, name.strip(), others.strip(), attend == "Yes ✅")
                            st.success("RSVP recorded! 🎉")
            else:
                st.error(f"Voting closed on {deadline}. See you next time! 🚫")
        except Exception:
            st.error("Invalid game date. Please check back later.")
