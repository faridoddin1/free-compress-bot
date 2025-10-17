import os
import tempfile
import requests
import time
import re
import threading
from pyrogram import Client, filters
from pyrogram.types import Message

import database

# Initialize the database
database.init_db()

# Get API keys from environment variables
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
API_TOKEN = os.environ.get("API_TOKEN")

# Check if all required environment variables are set
if not all([API_ID, API_HASH, API_TOKEN]):
    print("Please set the required environment variables: API_ID, API_HASH, API_TOKEN")
    exit()

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=API_TOKEN)

# In-memory dictionary to store user states
user_states = {}

def process_video(message: Message):
    user_id = message.from_user.id
    api_key = database.get_api_key(user_id)

    if not api_key:
        message.reply_text("You haven't set your API key yet. Please use the /start or /set_key command.")
        return

    if message.document:
        if not message.document.mime_type or "video" not in message.document.mime_type:
            message.reply_text("Please send a valid video file.")
            return
        if message.document.file_size > 100 * 1024 * 1024:
            message.reply_text("❌ File size is too large. Please send a file smaller than 100MB.")
            return
        file_id = message.document.file_id
        file_name = message.document.file_name or "video.mp4"
    else:
        if message.video.file_size > 100 * 1024 * 1024:
            message.reply_text("❌ File size is too large. Please send a file smaller than 100MB.")
            return
        file_id = message.video.file_id
        file_name = "video.mp4"

    processing_msg = message.reply_text("Processing your video... Please wait.")

    try:
        downloaded_file = app.download_media(file_id)

        # 1. Get upload task
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json',
        }
        response = requests.post('https://api.freeconvert.com/v1/process/import/upload', headers=headers)
        upload_task = response.json()

        # 2. Upload the file
        upload_url = upload_task['result']['form']['url']
        upload_parameters = upload_task['result']['form']['parameters']

        with open(downloaded_file, 'rb') as f:
            files = {'file': (os.path.basename(downloaded_file), f)}
            response = requests.post(upload_url, data=upload_parameters, files=files)

        # 3. Create compress task
        import_task_id = upload_task['id']
        compress_task_body = {
            'input': import_task_id,
            'input_format': downloaded_file.split('.')[-1],
            'output_format': downloaded_file.split('.')[-1],
            'options': {
                'video_codec_compress': 'libx265',
                'compress_video': 'by_video_quality',
                'video_compress_crf_x265': '28',
                'video_compress_speed': 'veryfast'
            }
        }
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }
        response = requests.post('https://api.freeconvert.com/v1/process/compress', json=compress_task_body, headers=headers)
        compress_task = response.json()
        compress_task_id = compress_task['id']

        # 4. Wait for the compression to finish
        while True:
            response = requests.get(f'https://api.freeconvert.com/v1/process/tasks/{compress_task_id}', headers=headers)
            task_status = response.json()
            if task_status['status'] == 'completed':
                break
            elif task_status['status'] == 'failed':
                processing_msg.edit_text(f"❌ Compression failed. Error: {task_status}")
                return
            time.sleep(5)

        # 5. Download the compressed file
        download_url = task_status['result']['url']
        output_file_name = download_url.split('/')[-1]
        
        with tempfile.NamedTemporaryFile(suffix=f'.{output_file_name.split(".")[-1]}', delete=False) as temp_file:
            response = requests.get(download_url, stream=True)
            if response.status_code == 200:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                temp_filename = temp_file.name
            else:
                processing_msg.edit_text(f"❌ Failed to download compressed file. Status code: {response.status_code}")
                return

        # Send the compressed video back
        processing_msg.edit_text("Compression complete! Sending compressed video...")
        message.reply_video(
            temp_filename,
            caption=f"✅ Video compressed successfully!\n📁 Original: {file_name}"
        )

        # Add the compressed file to the database
        database.add_compressed_file(user_id, file_name, temp_filename)

    except Exception as e:
        processing_msg.edit_text(f"❌ An error occurred: {str(e)}")
    finally:
        if 'downloaded_file' in locals() and os.path.exists(downloaded_file):
            os.remove(downloaded_file)
        if 'temp_filename' in locals() and os.path.exists(temp_filename):
            os.remove(temp_filename)

@app.on_message(filters.command("start"))
def start(client, message: Message):
    user_id = message.from_user.id
    api_key = database.get_api_key(user_id)
    if api_key:
        message.reply_text("Welcome back! Send your video files for compression.")
    else:
        message.reply_text("Welcome! To get started, please send me your Key. You can get it from https://www.freeconvert.com/account/api-tokens.")
        user_states[user_id] = "awaiting_api_key"

@app.on_message(filters.command("set_key"))
def set_key_command(client, message: Message):
    user_id = message.from_user.id
    message.reply_text("Please send me your new FREE_CONVERT_API_KEY.")
    user_states[user_id] = "awaiting_api_key"

@app.on_message(filters.text)
def handle_text(client, message: Message):
    user_id = message.from_user.id
    if user_states.get(user_id) == "awaiting_api_key":
        # A simple regex to validate the key format. This is not a foolproof validation.
        if re.match(r"^[a-z0-9_]+\.[a-f0-9]+\.[a-f0-9]+$", message.text):
            database.set_api_key(user_id, message.text)
            message.reply_text("✅ API key saved successfully! You can now send video files for compression.")
            user_states.pop(user_id, None)
        else:
            message.reply_text("❌ Invalid API key format. Please send a valid key.")
    elif user_states.get(user_id) == "awaiting_file_to_delete":
        try:
            file_id_to_delete = int(message.text)
            files = database.get_user_files(user_id)
            file_to_delete = None
            for file in files:
                if file[0] == file_id_to_delete:
                    file_to_delete = file
                    break
            
            if file_to_delete:
                # Delete from filesystem
                if os.path.exists(file_to_delete[2]):
                    os.remove(file_to_delete[2])
                # Delete from database
                database.delete_compressed_file(file_to_delete[0])
                message.reply_text("✅ File deleted successfully!")
            else:
                message.reply_text("❌ Invalid file number. Please try again.")
            user_states.pop(user_id, None)
        except ValueError:
            message.reply_text("❌ Invalid input. Please send a number.")

@app.on_message(filters.video | filters.document)
def handle_media(client, message: Message):
    thread = threading.Thread(target=process_video, args=(message,))
    thread.start()

@app.on_message(filters.command("my_files"))
def my_files(client, message: Message):
    user_id = message.from_user.id
    files = database.get_user_files(user_id)
    if not files:
        message.reply_text("You haven't compressed any files yet.")
        return

    response = "Your compressed files:\n\n"
    for file_id, original_name, compressed_name, date in files:
        response += f"- **ID:** {file_id}\n  **Original:** {original_name}\n  **Compressed:** {compressed_name}\n  **Date:** {date}\n"

    message.reply_text(response)

@app.on_message(filters.command("delete_file"))
def delete_file_command(client, message: Message):
    user_id = message.from_user.id
    files = database.get_user_files(user_id)
    if not files:
        message.reply_text("You haven't compressed any files yet.")
        return

    response = "Your compressed files:\n\n"
    for file_id, original_name, compressed_name, date in files:
        response += f"- **ID:** {file_id}\n  **Original:** {original_name}\n  **Compressed:** {compressed_name}\n  **Date:** {date}\n"
    response += "\nPlease reply with the ID of the file you want to delete."

    message.reply_text(response)
    user_states[user_id] = "awaiting_file_to_delete"

if __name__ == "__main__":
    print("Bot started...")
    app.run()