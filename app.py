from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextSendMessage
import os
from groq import Groq
from firebase import firebase
import json

app = Flask(__name__)

# 使用環境變量讀取憑證
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
FIREBASE_URL = os.getenv('FIREBASE_URL')

if not all([GROQ_API_KEY, CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, FIREBASE_URL]):
    raise ValueError("Missing one or more environment variables")

groq_client = Groq(api_key=GROQ_API_KEY)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")
    
    try:
        signature = request.headers['X-Line-Signature']
        handler.handle(body, signature)
        return 'OK'
    except InvalidSignatureError:
        app.logger.error("Invalid signature.")
        return 'Invalid signature', 400
    except Exception as e:
        app.logger.error(f"Error handling request: {str(e)}")
        return 'Internal Server Error', 500

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_id = event.source.user_id
        tk = event.reply_token
        msg_type = event.message.type

        fdb = firebase.FirebaseApplication(FIREBASE_URL, None)
        user_chat_path = f'chat/{user_id}'
        LLM = fdb.get(user_chat_path, None)

        if msg_type == 'text':
            msg = event.message.text

            if LLM is None:
                messages = []
            else:
                messages = LLM

            if msg == '!清空':
                reply_msg = TextSendMessage(text='對話歷史紀錄已經清空！')
                fdb.delete(user_chat_path, None)
            else:
                messages.append({"role": "user", "content": msg})
                response = groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "你只會繁體中文，回答任何問題時，都會使用繁體中文回答"
                        },
                        {
                            "role": "user",
                            "content": msg,
                        }
                    ],
                    model="llama3-8b-8192",
                )
                ai_msg = response.choices[0].message.content.replace('\n', '')
                messages.append({"role": "assistant", "content": ai_msg})
                reply_msg = TextSendMessage(text=ai_msg)
                fdb.put_async(user_chat_path, None, messages)

            line_bot_api.reply_message(tk, reply_msg)
        else:
            reply_msg = TextSendMessage(text='請傳送文字訊息!')
            line_bot_api.reply_message(tk, reply_msg)

    except Exception as e:
        app.logger.error(f"Error in message handling: {str(e)}")
        if 'tk' in locals():
            reply_msg = TextSendMessage(text='抱歉，發生錯誤，請稍後再試。')
            line_bot_api.reply_message(tk, reply_msg)

    return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
