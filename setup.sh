mkdir -p ~/.streamlit/

echo "\
[theme]\n\
primaryColor='#1f77b4'\n\
backgroundColor='#ffffff'\n\
secondaryBackgroundColor='#f0f2f6'\n\
textColor='#262730'\n\
[server]\n\
headless = true\n\
enableCORS=false\n\
port = $PORT\n\
[browser]\n\
gatherUsageStats = false\n\
" > ~/.streamlit/config.toml
