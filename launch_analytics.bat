@echo off
:: Activate the virtual environment
call venv\Scripts\activate

:: Start the Streamlit app and close the terminal window automatically
start /B streamlit run app.py