from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
from groq import Groq
import firebase_admin
from firebase_admin import credentials, db

app = Flask(__name__)

# Initialize LINE Bot API and Webhook Handler
line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

# Initialize Firebase Admin
cred = credentials.Certificate(os.environ['FIREBASE_CREDENTIALS'])
firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv('FIREBASE_URL')
})

# Initialize Groq Client
groq_client = Groq(api_key=os.environ['GROQ_API_KEY'])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_id = event.source.user_id
        user_chat_path = f'chat/{user_id}'
        chat_state_path = f'state/{user_id}'
        
        ref = db.reference(user_chat_path)
        LLM = ref.get()
        user_message = event.message.text
        if LLM is None:
            messages2 = []
        else:
            messages2 = LLM
        
        if user_message == "!清空":
            response_text = "對話歷史紀錄已經清空！"
            ref.delete()
        else:
            messages2.append({"role": "user", "content": user_message})
            response = groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "你只會繁體中文，回答任何問題時，都會使用繁體中文回答"
                    },
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ],
                model="llama3-8b-8192",
            )
            ai_msg = response.choices[0].message.content.replace('\n', '')
            messages2.append({"role": "assistant", "content": ai_msg})
            response_text = ai_msg
            
            # Update Firebase with the updated chat history
            ref.set(messages2)
    except Exception as e:
        app.logger.error(f"Error: {e}")
        response_text = "抱歉，目前無法處理您的請求。"

    message = TextSendMessage(text=response_text)
    line_bot_api.reply_message(event.reply_token, message)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
