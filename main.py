import os
from flask import Flask, request, Response, send_from_directory
from dotenv import load_dotenv
from threading import Thread
import logging
import json
import google.cloud.logging
from handlers.backblasts import ReminderBackblastsHandler

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')
googleLoggingClient = google.cloud.logging.Client()
googleLoggingClient.setup_logging()

backblasts = ReminderBackblastsHandler()

app = Flask(__name__)


@app.route('/')
def status():
    return Response('Service is running.', 200)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                          'favicon.ico',mimetype='image/vnd.microsoft.icon')


@app.route('/backblasts', methods=['POST'])
def process_all_backblast_reminders():
    thread = Thread(target=backblasts.check_for_missing_backblasts)
    thread.start()
    return Response(status=200)


if __name__ == "__main__":
    logging.info('Starting up app')
    load_dotenv()
    app.run(port=8080, debug=False)