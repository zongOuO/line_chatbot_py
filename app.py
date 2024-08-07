import json
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage
from firebase import firebase
import os
from groq import Groq

app = Flask(__name__)

# 設置環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
FIREBASE_URL = os.getenv('FIREBASE_URL')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# 初始化 LINE Bot API 和 Webhook Handler
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 初始化 Firebase 和 Groq 客戶端
fdb = firebase.FirebaseApplication(FIREBASE_URL, None)
groq_client = Groq(api_key=GROQ_API_KEY)

@app.route("/linebot", methods=['POST'])
def linebot():
    body = request.get_data(as_text=True)
    json_data = json.loads(body)
    try:
        signature = request.headers['X-Line-Signature']
        handler.handle(body, signature)

        # 取得事件
        event = json_data['events'][0]
        tk = event['replyToken']
        user_id = event['source']['userId']
        msg_type = event['message']['type']

        # 取得聊天記錄
        user_chat_path = f'chat/{user_id}'
        chatgpt = fdb.get(user_chat_path, None)

        if msg_type == 'text':
            msg = event['message']['text']

            if chatgpt is None:
                messages = []
            else:
                messages = chatgpt

            if msg == '!清空':
                reply_msg = TextSendMessage(text='對話歷史紀錄已經清空！')
                fdb.delete(user_chat_path, None)
                messages = []  # 清空對話紀錄

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
                            "content": msg
                        }
                    ],
                    model="llama3-8b-8192"
                )
                # 確認 API 回應的正確解析
                ai_msg = response.choices[0].message['content'].replace('\n', '') if response.choices else "未收到回應"
                messages.append({"role": "assistant", "content": ai_msg})
                reply_msg = TextSendMessage(text=ai_msg)
                # 更新 Firebase 中的對話紀錄
                fdb.put(user_chat_path, None, messages)

            line_bot_api.reply_message(tk, reply_msg)

        else:
            reply_msg = TextSendMessage(text='你傳的不是文字訊息呦')
            line_bot_api.reply_message(tk, reply_msg)

    except Exception as e:
        app.logger.error(f"處理消息時發生錯誤: {e}")
        line_bot_api.reply_message(tk, TextSendMessage(text='抱歉，目前無法處理您的請求。'))

    return 'OK'

if __name__ == "__main__":
    app.run(port=int(os.environ.get('PORT', 5000)))
