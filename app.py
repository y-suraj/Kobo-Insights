import datetime
import calendar
import plotly.express as px
import tkinter as tk
from tkinter import filedialog
import sqlite3
import pandas as pd
import tempfile
import os
import json
import streamlit as st

st.set_page_config(page_title="Kobo Analytics", layout="wide")
st.title("Kobo Reading Analytics")
import os

HISTORY_FILE = "path_history.json"

# Load recent paths from local file
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        recent_paths = json.load(f)
else:
    recent_paths = []

if "folder_path" not in st.session_state:
    st.session_state.folder_path = recent_paths[0] if recent_paths else ""

# UI for selecting paths in the Sidebar
with st.sidebar:
    st.header("Settings")
    # Dropdown to select from memory
    selected_recent = st.selectbox("Recent Kobo folders:", [""] + recent_paths, index=0)
    if selected_recent:
        st.session_state.folder_path = selected_recent
        
    st.divider()
    if st.button("Browse new folder", use_container_width=True):
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        new_folder = filedialog.askdirectory(master=root, title="Select your .kobo folder")
        
        if new_folder:
            st.session_state.folder_path = new_folder
            if new_folder in recent_paths:
                recent_paths.remove(new_folder)
            recent_paths.insert(0, new_folder)
            recent_paths = recent_paths[:5]
            
            with open(HISTORY_FILE, "w") as f:
                json.dump(recent_paths, f)
            st.rerun()

# Use the path if one has been selected
if st.session_state.folder_path:
    folder_path = st.session_state.folder_path
    st.write(f"**Selected folder:** {folder_path}")
    
    # Construct the expected path to the database
    db_path = os.path.join(folder_path, "KoboReader.sqlite")

    if os.path.exists(db_path):
            # Connect directly to the local file
            conn = sqlite3.connect(db_path)
            
            # Tell SQLite to ignore malformed UTF-8 bytes in the Kobo database
            conn.text_factory = lambda b: b.decode(errors='ignore') 
            
            try:
                # Load the raw event logs
                df = pd.read_sql_query("SELECT * FROM Event", conn)
                st.success(f"Successfully connected to database!")
                # ==========================================
                # 1. DATA PROCESSING (Crunch all numbers first)
                # ==========================================
                
                # KPIs and Currently Reading Data
                content_df = pd.read_sql_query("SELECT Title, ___PercentRead, TimeSpentReading, ReadStatus FROM content WHERE ContentType = 6 AND Title IS NOT NULL", conn)
                books_started = len(content_df[content_df['___PercentRead'] > 0])
                books_finished = len(content_df[content_df['ReadStatus'] == 2])
                total_hours = content_df['TimeSpentReading'].sum() / 3600
                active_books = content_df[(content_df['___PercentRead'] > 0) & (content_df['___PercentRead'] < 100)].sort_values(by='TimeSpentReading', ascending=False)
                
                # Book Summary Data
                df['Book Title'] = df['ContentID'].apply(lambda x: str(x).split('/')[-1].replace('%20', ' ').replace('.kepub.epub', '').replace('.epub', '') if pd.notnull(x) else 'Unknown')
                books_df = df[df['Book Title'] != 'Unknown']
                book_summary = books_df.groupby('Book Title').agg(Total_Interactions=('EventCount', 'sum'), First_Opened=('FirstOccurrence', 'min'), Last_Read=('LastOccurrence', 'max')).reset_index()
                
                # Streaks and Calendar Data
                try:
                    dates_df = pd.read_sql_query("SELECT Timestamp FROM AnalyticsEvents", conn)
                    all_dates = pd.to_datetime(dates_df['Timestamp']).dt.date.dropna().tolist()
                except Exception:
                    all_dates = []
                all_dates.extend(pd.to_datetime(df['FirstOccurrence']).dt.date.dropna().tolist())
                all_dates.extend(pd.to_datetime(df['LastOccurrence']).dt.date.dropna().tolist())
                active_days = sorted(list(set(all_dates)))
                
                if active_days:
                    longest_streak, current_count = 0, 1
                    for i in range(1, len(active_days)):
                        if (active_days[i] - active_days[i-1]).days == 1: current_count += 1
                        else: longest_streak, current_count = max(longest_streak, current_count), 1
                    longest_streak = max(longest_streak, current_count)
                    
                    current_streak = 1
                    for i in range(len(active_days)-2, -1, -1):
                        if (active_days[i+1] - active_days[i]).days == 1: current_streak += 1
                        else: break
                else:
                    longest_streak, current_streak = 0, 0
                    
                # ==========================================
                # 2. TABBED UI DASHBOARD (Render the visuals)
                # ==========================================
                
                tab_overview, tab_habits, tab_deep_dive = st.tabs(["📊 Overview & Streaks", "📈 Reading Habits", "🔍 Deep Dive"])
                
                # --- TAB 1: OVERVIEW ---
                with tab_overview:
                    st.subheader("Lifetime Reading Snapshot")
                    kpi1, kpi2, kpi3 = st.columns(3)
                    kpi1.metric(label="Books Started", value=books_started)
                    kpi2.metric(label="Books Finished", value=books_finished)
                    kpi3.metric(label="Total Hours Read", value=f"{total_hours:.1f} hrs")
                    
                    st.divider()
                    st.subheader("Currently Reading")
                    if not active_books.empty:
                        for _, row in active_books.head(5).iterrows():
                            pct = min(int(row['___PercentRead']), 100)
                            st.write(f"**{row['Title']}** - {pct}%")
                            st.progress(pct)
                    else:
                        st.info("No books currently in progress.")
                    
                    st.divider()
                    streak_col, cal_col = st.columns([1, 2]) # Place streaks and calendar side-by-side
                    
                    with streak_col:
                        st.subheader("Reading Streaks")
                        st.metric(label="Current Active Streak", value=f"{current_streak} Days")
                        st.write("") 
                        st.metric(label="All-Time Longest Streak", value=f"{longest_streak} Days")
                        
                    with cal_col:
                        st.subheader("Activity Calendar")
                        if active_days:
                            unique_months = sorted(list(set([(d.year, d.month) for d in active_days])), reverse=True)
                            month_options = [datetime.date(y, m, 1).strftime('%B %Y') for y, m in unique_months]
                            if "cal_month_idx" not in st.session_state or st.session_state.cal_month_idx >= len(month_options):
                                st.session_state.cal_month_idx = 0
                                
                            cal_c1, cal_c2, cal_c3 = st.columns([1, 3, 1])
                            with cal_c1:
                                if st.button("◀ Prev", use_container_width=True, disabled=(st.session_state.cal_month_idx >= len(month_options) - 1)):
                                    st.session_state.cal_month_idx += 1
                                    st.rerun()
                            with cal_c2:
                                selected_month_str = month_options[st.session_state.cal_month_idx]
                                st.markdown(f"<div style='text-align: center; font-size: 16px; font-weight: bold; padding-top: 5px;'>{selected_month_str}</div>", unsafe_allow_html=True)
                            with cal_c3:
                                if st.button("Next ▶", use_container_width=True, disabled=(st.session_state.cal_month_idx <= 0)):
                                    st.session_state.cal_month_idx -= 1
                                    st.rerun()
                            
                            selected_date = datetime.datetime.strptime(selected_month_str, '%B %Y').date()
                            month_cal = calendar.Calendar(firstweekday=0).monthdatescalendar(selected_date.year, selected_date.month)
                            
                            md = "| Mon | Tue | Wed | Thu | Fri | Sat | Sun |\n|---|---|---|---|---|---|---|\n"
                            for week in month_cal:
                                row = "|"
                                for day in week:
                                    if day.month == selected_date.month:
                                        row += f" **{day.day}** 🔥 |" if day in active_days else f" {day.day} |"
                                    else:
                                        row += " |"
                                md += row + "\n"
                            st.markdown(md)
                        else:
                            st.info("No calendar data available.")

                # --- TAB 2: HABITS ---
                with tab_habits:
                    col_bar, col_pie = st.columns(2)
                    top_books = book_summary.sort_values(by='Total_Interactions', ascending=False).head(10)
                    top_books['Short Title'] = top_books['Book Title'].apply(lambda x: (x[:25] + '...') if len(x) > 25 else x)
                    
                    with col_bar:
                        st.markdown("**Top 10 Books by Total Interactions**")
                        fig_bar = px.bar(top_books, x='Total_Interactions', y='Short Title', orientation='h', color='Total_Interactions', color_continuous_scale='Viridis', hover_name='Book Title', labels={'Total_Interactions': 'Total Interactions', 'Short Title': ''})
                        fig_bar.update_layout(yaxis={'categoryorder':'total ascending', 'showticklabels': True, 'title': None}, xaxis={'title': 'Total Interactions'}, coloraxis_colorbar={'title': 'Interactions'}, showlegend=False)
                        st.plotly_chart(fig_bar, use_container_width=True)
                        
                    with col_pie:
                        st.markdown("**Interaction Share (Top 10)**")
                        fig_pie = px.pie(top_books, values='Total_Interactions', names='Book Title', hole=0.4, color_discrete_sequence=px.colors.sequential.Viridis)
                        fig_pie.update_traces(textposition='inside', textinfo='percent')
                        st.plotly_chart(fig_pie, use_container_width=True)
                        
                    st.divider()
                    col_time, col_day = st.columns(2) # Place time charts side-by-side
                    
                    with col_time:
                        st.markdown("**Time Spent Reading**")
                        content_df['Hours Read'] = content_df['TimeSpentReading'] / 3600
                        top_time_books = content_df[content_df['Hours Read'] > 0].sort_values(by='Hours Read', ascending=False).head(10)
                        top_time_books['Short Title'] = top_time_books['Title'].apply(lambda x: (str(x)[:25] + '...') if len(str(x)) > 25 else str(x))
                        fig_time = px.bar(top_time_books, x='Hours Read', y='Short Title', orientation='h', color='Hours Read', color_continuous_scale='Inferno', hover_name='Title', labels={'Hours Read': 'Total Hours', 'Short Title': ''})
                        fig_time.update_layout(yaxis={'categoryorder':'total ascending', 'title': None}, xaxis={'title': 'Hours Read'}, coloraxis_colorbar={'title': 'Hours'}, showlegend=False)
                        st.plotly_chart(fig_time, use_container_width=True)
                        
                    with col_day:
                        st.markdown("**When Do You Read?**")
                        books_df['Hour'] = pd.to_datetime(books_df['FirstOccurrence']).dt.hour
                        hour_counts = books_df['Hour'].value_counts().reset_index()
                        hour_counts.columns = ['Hour', 'Interactions']
                        hour_counts['Time'] = hour_counts['Hour'].apply(lambda x: datetime.time(int(x)).strftime('%I %p') if pd.notnull(x) else "Unknown")
                        fig_hours = px.bar(hour_counts.sort_values(by='Hour'), x='Time', y='Interactions', color='Interactions', color_continuous_scale='Sunset', labels={'Time': 'Time of Day'})
                        fig_hours.update_layout(xaxis={'title': None}, yaxis={'title': 'Activity Level'}, showlegend=False)
                        st.plotly_chart(fig_hours, use_container_width=True)

                # --- TAB 3: DEEP DIVE ---
                with tab_deep_dive:
                    st.markdown("**Reading Activity Timeline**")
                    timeline_data = book_summary.dropna(subset=['First_Opened'])
                    fig_timeline = px.scatter(timeline_data, x='First_Opened', y='Book Title', size='Total_Interactions', color='Total_Interactions', color_continuous_scale='Viridis', hover_name='Book Title', labels={'First_Opened': 'Started On', 'Total_Interactions': 'Total Interactions', 'Book Title': 'Book'})
                    fig_timeline.update_layout(yaxis={'visible': False, 'showticklabels': False}, xaxis={'title': 'Date First Opened'}, coloraxis_colorbar={'title': 'Interactions'})
                    fig_timeline.update_traces(hovertemplate="<b>%{hovertext}</b><br><br>Started On: %{x}<br>Interactions: %{marker.size}<extra></extra>")
                    st.plotly_chart(fig_timeline, use_container_width=True)
                    
                    st.divider()
                    selected_deep_dive = st.selectbox("Select a specific book to analyze:", [""] + sorted(books_df['Book Title'].unique().tolist()))
                    if selected_deep_dive:
                        deep_dive_df = books_df[books_df['Book Title'] == selected_deep_dive]
                        dd_c1, dd_c2, dd_c3 = st.columns(3)
                        dd_c1.metric("Total Event Interactions", deep_dive_df['EventCount'].sum())
                        try:
                            dd_c2.metric("Date First Opened", pd.to_datetime(deep_dive_df['FirstOccurrence'].min()).strftime('%b %d, %Y'))
                            dd_c3.metric("Date Last Read", pd.to_datetime(deep_dive_df['LastOccurrence'].max()).strftime('%b %d, %Y'))
                        except Exception:
                            dd_c2.metric("Date First Opened", "Unknown")
                            dd_c3.metric("Date Last Read", "Unknown")
            except Exception as e:
                st.error(f"Error reading the database: {e}")
            finally:
                conn.close()
    else:
        st.warning(f"Could not find 'KoboReader.sqlite' inside {folder_path}. Please check the path.")