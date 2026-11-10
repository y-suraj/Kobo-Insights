import tkinter as tk
from tkinter import filedialog
import sqlite3
import pandas as pd
import tempfile
import os
import streamlit as st

st.title("Kobo Reading Analytics")
import os

# Initialize session state to remember the path
if "folder_path" not in st.session_state:
    st.session_state.folder_path = ""

# Create the browse button
if st.button("Browse for .kobo folder"):
    # Set up a hidden tkinter window
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes('-topmost', 1) # Force the dialog to appear above the browser
    
    # Open the folder picker
    selected_folder = filedialog.askdirectory(master=root, title="Select your .kobo folder")
    
    if selected_folder:
        st.session_state.folder_path = selected_folder

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
                
                # 4. Display the clean summary table across the full width of the app
                st.dataframe(book_summary, use_container_width=True)
                
            except Exception as e:
                st.error(f"Error reading the database: {e}")
            finally:
                conn.close()
    else:
        st.warning(f"Could not find 'KoboReader.sqlite' inside {folder_path}. Please check the path.")