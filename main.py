"""Arranca la app en el navegador: servidor local (app/server.py) + frontend
compilado de web/dist."""

import threading
import webbrowser

import uvicorn

HOST, PORT = "127.0.0.1", 8765

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run("app.server:app", host=HOST, port=PORT, log_level="warning")
