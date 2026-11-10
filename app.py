import sqlite3
import pandas as pd
import tempfile
import os
import streamlit as st

st.title("Kobo Reading Analytics")
uploaded_file = st.file_uploader("Upload your KoboReader.sqlite file", type=["sqlite", "sqlite3", "db", ""])

if uploaded_file is not None:
    # Save the uploaded file temporarily so SQLite can read it from the local path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        temp_path = tmp_file.name

    # Connect to the temporary database copy
    conn = sqlite3.connect(temp_path)
    
    try:
        # Load the raw event logs into a Pandas DataFrame
        df = pd.read_sql_query("SELECT * FROM Event", conn)
        st.success("Database connected successfully!")
        
        st.subheader("Raw Data Preview")
        st.dataframe(df.head(15))
        
    except Exception as e:
        st.error(f"Error reading the database: {e}")
    finally:
        # Close connection and clean up the temp file
        conn.close()
        os.remove(temp_path)