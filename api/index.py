import sys
import os
import traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

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
