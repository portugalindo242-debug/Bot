from flask import Flask
from threading import Thread

app = Flask("keep_alive")


@app.route("/")
def home():
    return "O bot está online!"


def run():
    # O Render define a porta a usar na variável de ambiente PORT
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    """Sobe um servidor web numa thread separada, só para o Render
    (ou um serviço tipo UptimeRobot) ter algo para 'bater' e não deixar
    o processo dormir por inatividade."""
    t = Thread(target=run)
    t.daemon = True
    t.start()
