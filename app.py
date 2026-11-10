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

