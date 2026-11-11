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

# UI for selecting paths
col_a, col_b = st.columns([3, 1])

with col_a:
    # Dropdown to select from memory
    selected_recent = st.selectbox("Recent Kobo folders:", [""] + recent_paths, index=0)
    if selected_recent:
        st.session_state.folder_path = selected_recent

with col_b:
    st.write("") # Spacing to align button with dropdown
    st.write("")
    if st.button("Browse new folder"):
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        new_folder = filedialog.askdirectory(master=root, title="Select your .kobo folder")
        
        if new_folder:
            st.session_state.folder_path = new_folder
            # Save to history, keeping only the 5 most recent
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
                # --- LIFETIME KPI CARDS ---
                # Load the 'content' table which stores actual reading time and progress
                # ContentType 6 generally isolates actual books rather than chapters/dictionaries
                content_df = pd.read_sql_query(
                    "SELECT Title, ___PercentRead, TimeSpentReading, ReadStatus FROM content WHERE ContentType = 6 AND Title IS NOT NULL", 
                    conn
                )
                
                # Calculate metrics (TimeSpentReading is logged in seconds)
                books_started = len(content_df[content_df['___PercentRead'] > 0])
                books_finished = len(content_df[content_df['ReadStatus'] == 2]) # Status 2 = Finished
                total_hours = content_df['TimeSpentReading'].sum() / 3600
                
                st.subheader("Lifetime Reading Snapshot")
                kpi1, kpi2, kpi3 = st.columns(3)
                
                kpi1.metric(label="Books Started", value=books_started)
                kpi2.metric(label="Books Finished", value=books_finished)
                kpi3.metric(label="Total Hours Read", value=f"{total_hours:.1f} hrs")
                
                st.divider()
                
                # --- NEW: CURRENTLY READING PROGRESS BARS ---
                st.subheader("Currently Reading")
                
                # Filter for active books (progress between 1% and 99%)
                active_books = content_df[(content_df['___PercentRead'] > 0) & (content_df['___PercentRead'] < 100)].sort_values(by='TimeSpentReading', ascending=False)
                
                if not active_books.empty:
                    for _, row in active_books.head(5).iterrows(): # Show top 5 active books
                        pct = min(int(row['___PercentRead']), 100) # Cap at 100 for the UI
                        st.write(f"**{row['Title']}** - {pct}%")
                        st.progress(pct)
                else:
                    st.info("No books currently in progress.")
                
                # 1. Sweep the database for every available timestamp to reconstruct active days
                try:
                    # AnalyticsEvents holds detailed telemetry if the device hasn't purged it
                    dates_df = pd.read_sql_query("SELECT Timestamp FROM AnalyticsEvents", conn)
                    all_dates = pd.to_datetime(dates_df['Timestamp']).dt.date.dropna().tolist()
                except Exception:
                    all_dates = []
                
                # Add First/Last occurrence from the Event table as a fallback
                all_dates.extend(pd.to_datetime(df['FirstOccurrence']).dt.date.dropna().tolist())
                all_dates.extend(pd.to_datetime(df['LastOccurrence']).dt.date.dropna().tolist())
                
                # Deduplicate and sort the dates
                active_days = sorted(list(set(all_dates)))
                
                if active_days:
                    # Calculate longest all-time streak
                    longest_streak = 0
                    current_count = 1
                    for i in range(1, len(active_days)):
                        if (active_days[i] - active_days[i-1]).days == 1:
                            current_count += 1
                        else:
                            longest_streak = max(longest_streak, current_count)
                            current_count = 1
                    longest_streak = max(longest_streak, current_count)
                    
                    # Calculate current streak (counting backwards from your most recent active day)
                    current_streak = 1
                    for i in range(len(active_days)-2, -1, -1):
                        if (active_days[i+1] - active_days[i]).days == 1:
                            current_streak += 1
                        else:
                            break
                            
                    latest_date = active_days[-1]
                else:
                    longest_streak, current_streak = 0, 0
                    latest_date = datetime.date.today()
                    
                # 2. Display the Streak KPIs
                streak_col1, streak_col2 = st.columns(2)
                streak_col1.metric(label="Current Active Streak", value=f"{current_streak} Days")
                streak_col2.metric(label="All-Time Longest Streak", value=f"{longest_streak} Days")
                
                st.write("") # Spacing
                
                # 3. Generate the Fire Emoji Calendar with Arrow Navigation
                if active_days:
                    # Extract all unique months from your activity history, sorted newest to oldest
                    unique_months = sorted(list(set([(d.year, d.month) for d in active_days])), reverse=True)
                    month_options = [datetime.date(y, m, 1).strftime('%B %Y') for y, m in unique_months]
                    
                    # Initialize calendar index in session state (0 is the newest month)
                    if "cal_month_idx" not in st.session_state:
                        st.session_state.cal_month_idx = 0
                        
                    # Failsafe in case folder changes and fewer months exist
                    if st.session_state.cal_month_idx >= len(month_options):
                        st.session_state.cal_month_idx = 0
                        
                    # Create a 3-column layout for the arrows and the month label
                    cal_col1, cal_col2, cal_col3 = st.columns([1, 3, 1])
                    
                    with cal_col1:
                        # Left arrow goes back in time (increases index in our newest-to-oldest list)
                        # The button automatically disables if there is no older data
                        if st.button("◀ Previous", use_container_width=True, disabled=(st.session_state.cal_month_idx >= len(month_options) - 1)):
                            st.session_state.cal_month_idx += 1
                            st.rerun()
                            
                    with cal_col2:
                        # Display the currently selected month centered between the buttons
                        selected_month_str = month_options[st.session_state.cal_month_idx]
                        st.markdown(f"<div style='text-align: center; font-size: 18px; font-weight: bold; padding-top: 5px;'>{selected_month_str}</div>", unsafe_allow_html=True)
                        
                    with cal_col3:
                        # Right arrow goes forward in time (decreases index)
                        # Disables if we are already viewing the most recent month
                        if st.button("Next ▶", use_container_width=True, disabled=(st.session_state.cal_month_idx <= 0)):
                            st.session_state.cal_month_idx -= 1
                            st.rerun()
                    
                    # Generate the calendar for the selected month
                    selected_date = datetime.datetime.strptime(selected_month_str, '%B %Y').date()
                    cal = calendar.Calendar(firstweekday=0) # Monday start
                    month_cal = cal.monthdatescalendar(selected_date.year, selected_date.month)
                    
                    # Build a Markdown table row by row
                    md = "| Mon | Tue | Wed | Thu | Fri | Sat | Sun |\n|---|---|---|---|---|---|---|\n"
                    for week in month_cal:
                        row = "|"
                        for day in week:
                            if day.month == selected_date.month:
                                if day in active_days:
                                    row += f" **{day.day}** 🔥 |"
                                else:
                                    row += f" {day.day} |"
                            else:
                                row += " |" # Empty cell
                        md += row + "\n"
                    
                    # Render the markdown table
                    st.markdown(md)
                else:
                    st.info("No reading activity found to generate a calendar.")
                st.divider()
                st.subheader("Book Summary")
                
                # 1. Clean the ContentID to extract readable book titles
                # This splits the file path, takes the last part, and removes URL formatting/extensions
                df['Book Title'] = df['ContentID'].apply(
                    lambda x: str(x).split('/')[-1].replace('%20', ' ').replace('.kepub.epub', '').replace('.epub', '') if pd.notnull(x) else 'Unknown'
                )
                
                # 2. Remove system events (keep only rows attached to an actual book)
                books_df = df[df['Book Title'] != 'Unknown']
                
                # 3. Group the data by book to calculate basic metrics
                book_summary = books_df.groupby('Book Title').agg(
                    Total_Interactions=('EventCount', 'sum'),
                    First_Opened=('FirstOccurrence', 'min'),
                    Last_Read=('LastOccurrence', 'max')
                ).reset_index()
                
                # --- VISUAL DASHBOARD ---
                
                # Sort books by interactions to find your most read books
                top_books = book_summary.sort_values(by='Total_Interactions', ascending=False).head(10)
                
                st.divider()
                st.subheader("Reading Analytics Dashboard")
                
                # Create a two-column layout for the charts
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Top 10 Books by Total Interactions**")
                    
                    # Stricter 25-character truncation so it fits perfectly in the column layout
                    top_books['Short Title'] = top_books['Book Title'].apply(lambda x: (x[:25] + '...') if len(x) > 25 else x)
                    
                    # Create the horizontal bar chart using standard outside labels
                    fig_bar = px.bar(
                        top_books, 
                        x='Total_Interactions', 
                        y='Short Title', 
                        orientation='h',
                        color='Total_Interactions',
                        color_continuous_scale='Viridis',
                        hover_name='Book Title', # Full name still appears cleanly on hover
                        labels={'Total_Interactions': 'Total Interactions', 'Short Title': ''} 
                    )
                    
                    # Restore clean Y-axis labels and let Plotly auto-manage the fit
                    fig_bar.update_layout(
                        yaxis={'categoryorder':'total ascending', 'showticklabels': True, 'title': None}, 
                        xaxis={'title': 'Total Interactions'},
                        coloraxis_colorbar={'title': 'Interactions'},
                        showlegend=False
                    )
                    
                    st.plotly_chart(fig_bar, use_container_width=True)
                with col2:
                    st.markdown("**Interaction Share (Top 10)**")
                    # Create a donut chart
                    fig_pie = px.pie(
                        top_books, 
                        values='Total_Interactions', 
                        names='Book Title',
                        hole=0.4,
                        color_discrete_sequence=px.colors.sequential.Viridis
                    )
                    fig_pie.update_traces(textposition='inside', textinfo='percent')
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                st.divider()
                
                # Timeline Scatter Plot across the full width at the bottom
                st.markdown("**Reading Activity Timeline (When books were first opened)**")
                timeline_data = book_summary.dropna(subset=['First_Opened'])
                
                fig_timeline = px.scatter(
                    timeline_data, 
                    x='First_Opened', 
                    y='Book Title',
                    size='Total_Interactions',
                    color='Total_Interactions',
                    color_continuous_scale='Viridis',
                    hover_name='Book Title',
                    # FIX: Map variable names to clean UI labels
                    labels={
                        'First_Opened': 'Started On',
                        'Total_Interactions': 'Total Interactions',
                        'Book Title': 'Book'
                    }
                )
                
                # FIX: Clean up the axes and colorbar
                fig_timeline.update_layout(
                    yaxis={'visible': False, 'showticklabels': False},
                    xaxis={'title': 'Date First Opened'},
                    coloraxis_colorbar={'title': 'Interactions'}
                )
                
                # FIX: Build a custom, clean hover tooltip without repetitive text
                fig_timeline.update_traces(
                    hovertemplate="<b>%{hovertext}</b><br><br>Started On: %{x}<br>Interactions: %{marker.size}<extra></extra>"
                )
                
                st.plotly_chart(fig_timeline, use_container_width=True)
                # --- TIME SPENT ANALYTICS ---
                st.divider()
                st.subheader("Time Spent Reading")
                
                # Convert the raw seconds into hours and filter out unread books
                content_df['Hours Read'] = content_df['TimeSpentReading'] / 3600
                top_time_books = content_df[content_df['Hours Read'] > 0].sort_values(by='Hours Read', ascending=False).head(10)
                
                # Apply the same 25-character UI truncation to the official book titles
                top_time_books['Short Title'] = top_time_books['Title'].apply(lambda x: (str(x)[:25] + '...') if len(str(x)) > 25 else str(x))
                
                # Create a horizontal bar chart with a distinct color scale (Inferno)
                fig_time = px.bar(
                    top_time_books, 
                    x='Hours Read', 
                    y='Short Title', 
                    orientation='h',
                    color='Hours Read',
                    color_continuous_scale='Inferno',
                    hover_name='Title',
                    labels={'Hours Read': 'Total Hours', 'Short Title': ''} 
                )
                
                fig_time.update_layout(
                    yaxis={'categoryorder':'total ascending', 'showticklabels': True, 'title': None}, 
                    xaxis={'title': 'Hours Read'},
                    coloraxis_colorbar={'title': 'Hours'},
                    showlegend=False
                )
                
                st.plotly_chart(fig_time, use_container_width=True)
                # --- NEW: TIME OF DAY ANALYSIS ---
                st.divider()
                st.subheader("When Do You Read?")
                
                # Extract the hour from the FirstOccurrence timestamp
                books_df['Hour'] = pd.to_datetime(books_df['FirstOccurrence']).dt.hour
                hour_counts = books_df['Hour'].value_counts().reset_index()
                hour_counts.columns = ['Hour', 'Interactions']
                hour_counts = hour_counts.sort_values(by='Hour')
                
                # Format 24h time to 12h AM/PM for the UI
                hour_counts['Time'] = hour_counts['Hour'].apply(lambda x: datetime.time(int(x)).strftime('%I %p') if pd.notnull(x) else "Unknown")
                
                # Create a bar chart with a 'Sunset' color gradient
                fig_hours = px.bar(
                    hour_counts, 
                    x='Time', 
                    y='Interactions',
                    color='Interactions',
                    color_continuous_scale='Sunset',
                    labels={'Time': 'Time of Day'}
                )
                fig_hours.update_layout(xaxis={'title': None}, yaxis={'title': 'Activity Level'}, showlegend=False)
                st.plotly_chart(fig_hours, use_container_width=True)
            # --- NEW: SINGLE BOOK DEEP DIVE ---
                st.divider()
                st.subheader("Deep Dive: Single Book Analysis")
                
                # Dropdown to isolate a specific title
                selected_deep_dive = st.selectbox("Select a specific book to analyze:", [""] + sorted(books_df['Book Title'].unique().tolist()))
                
                if selected_deep_dive:
                    deep_dive_df = books_df[books_df['Book Title'] == selected_deep_dive]
                    
                    dd_col1, dd_col2, dd_col3 = st.columns(3)
                    dd_col1.metric("Total Event Interactions", deep_dive_df['EventCount'].sum())
                    
                    # Extract first and last read dates safely
                    try:
                        first_read = pd.to_datetime(deep_dive_df['FirstOccurrence'].min()).strftime('%b %d, %Y')
                        last_read = pd.to_datetime(deep_dive_df['LastOccurrence'].max()).strftime('%b %d, %Y')
                    except Exception:
                        first_read, last_read = "Unknown", "Unknown"
                        
                    dd_col2.metric("Date First Opened", first_read)
                    dd_col3.metric("Date Last Read", last_read)
            except Exception as e:
                st.error(f"Error reading the database: {e}")
            finally:
                conn.close()
    else:
        st.warning(f"Could not find 'KoboReader.sqlite' inside {folder_path}. Please check the path.")