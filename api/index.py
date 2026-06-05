import sys
import os
import traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

# Load variables from a local .env file for development. On Vercel this is a
# no-op (no .env file is deployed); the real values come from project env vars.
load_dotenv()

from flask import Flask, request, Response
from bot.handlers.message import on_update

app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        on_update(request.get_json(force=True, silent=True) or {})
    except Exception:
        traceback.print_exc()
    return Response("OK", 200)


@app.route("/webhook", methods=["GET"])
def health():
    return Response("NS Deferment Bot is running.", 200)
