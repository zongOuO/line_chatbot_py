from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
from groq import Groq
from firebase import firebase


app = Flask(__name__)

# Initialize LINE Bot API and Webhook Handler
line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])
firebase_url = os.getenv('FIREBASE_URL')

# Initialize Groq Client
groq_client = Groq(api_key=os.environ['GROQ_API_KEY'])

@app.route("/callback", methods=['POST'])
def callback():
    # Get X-Line-Signature header value
    signature = request.headers.get('X-Line-Signature', '')
    # Get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # Handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        fdb = firebase.FirebaseApplication(firebase_url, None)
        user_id = event.source.user_id
        user_chat_path = f'chat/{user_id}'
        chat_history = fdb.get(user_chat_path, 'messages')
        user_message = event.message.text
        
        if chat_history is None:
            chat_history = []
        
        if user_message == "!清空":
            response_text = "對話歷史紀錄已經清空！"
            fdb.delete(user_chat_path, 'messages')
            chat_history = []
        else:
            # 添加用戶消息到歷史記錄
            chat_history.append({"role": "user", "content": user_message})
            
            # 準備發送給 Groq 的消息列表
            messages_for_groq = [
                {"role": "system", "content": "你只會繁體中文，回答任何問題時，都會使用繁體中文回答"}
            ]
            # 添加完整的歷史對話
            messages_for_groq.extend(chat_history)
            
            try:
                response = groq_client.chat.completions.create(
                    messages=messages_for_groq,
                    model="llama3-8b-8192",
                )
                ai_msg = response.choices[0].message.content.replace('\n', '')
                
                # 添加 AI 回覆到歷史記錄
                chat_history.append({"role": "assistant", "content": ai_msg})
                response_text = ai_msg
                
                # 更新firebase中的對話紀錄
                fdb.put(user_chat_path, 'messages', chat_history)
            except Exception as e:
                app.logger.error(f"Groq API error: {e}")
                response_text = "抱歉，AI 回應時發生錯誤。可能是因為對話歷史過長，請嘗試清空對話歷史。"
    except Exception as e:
        app.logger.error(f"General error: {e}")
        response_text = "抱歉，目前無法處理您的請求。"

    message = TextSendMessage(text=response_text)
    line_bot_api.reply_message(event.reply_token, message)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
