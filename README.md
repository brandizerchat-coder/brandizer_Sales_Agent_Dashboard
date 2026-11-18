# BRANDIZER · Sales Pipeline dashboard

Streamlit + pandas + Plotly. Reads 3 Google Sheets tabs published as CSV:
leads_all (Leads file), outreach_report and activity (audit file).

Files: app.py · requirements.txt · .streamlit/config.toml (brand theme, light + dark) · assets/logo.png (optional, white logo for the black header)

Secrets (Streamlit Cloud → App settings → Secrets), never in GitHub:

    [data]
    leads_all = "<published CSV link>"
    outreach_report = "<published CSV link>"
    activity = "<published CSV link>"

Data refreshes every 5 minutes (Google publishes sheet changes within ~5 minutes).
Light / dark: ⋮ menu → Settings → Theme (default follows the device).
