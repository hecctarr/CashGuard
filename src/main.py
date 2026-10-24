"""
CashGuard Risk - application entry point.

Starts the Streamlit web app (src/app.py). Replit runs this file via .replit.
Set WHATSAPP_WEBHOOK=1 to also start the WhatsApp webhook (src/whatsapp_webhook.py)
on WEBHOOK_PORT (default 5055).
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    if os.environ.get("WHATSAPP_WEBHOOK") == "1":
        env = {**os.environ, "PORT": os.environ.get("WEBHOOK_PORT", "5055")}
        subprocess.Popen([sys.executable, os.path.join(HERE, "whatsapp_webhook.py")], env=env)

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", os.path.join(HERE, "app.py"),
        "--server.port", os.environ.get("PORT", "8501"),
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--theme.base", "light",
        "--theme.primaryColor", "#152846",
        "--theme.backgroundColor", "#F7F8FA",
        "--theme.secondaryBackgroundColor", "#F2F3F5",
        "--theme.textColor", "#1F2329",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
