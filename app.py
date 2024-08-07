from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
from groq import Groq
from firebase import firebase
import requests

app = Flask(__name__)

# 初始化 LINE Bot API 和 Webhook Handler
line_bot_api = LineBotApi(os.environ['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['CHANNEL_SECRET'])
firebase_url = os.getenv('FIREBASE_URL')

# 初始化 Groq 客戶端
groq_client = Groq(api_key=os.environ['GROQ_API_KEY'])

@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭值
    signature = request.headers.get('X-Line-Signature', '')
    # 取得請求內容
    body = request.get_data(as_text=True)
    app.logger.info("請求內容: " + body)

    # 處理 webhook 內容
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    fdb = firebase.FirebaseApplication(firebase_url, None)
    user_id = event.source.user_id
    user_chat_path = f'chat/{user_id}'
    user_message = event.message.text

    try:
        # 從 Firebase 取得聊天記錄
        response = fdb.get(user_chat_path, None)
        app.logger.info(f"Firebase 回應: {response}")

        if response is None:
            messages2 = []
        else:
            messages2 = response

        # 處理特殊命令
        if user_message == "!清空":
            response_text = "對話歷史紀錄已經清空！"
            fdb.delete(user_chat_path, None)
        else:
            # 將使用者消息加入聊天記錄
            messages2.append({"role": "user", "content": user_message})

            # 向 Groq API 請求完成結果
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

            # 提取回應文本
            app.logger.info(f"Groq API 回應: {response}")
            response_text = response.choices[0].message.content if response.choices else "未收到回應"

            # 更新聊天記錄
            messages2.append({"role": "assistant", "content": response_text})
            fdb.put_async(user_chat_path, None, messages2)
    except requests.exceptions.JSONDecodeError as e:
        app.logger.error(f"JSON 解碼錯誤: {e}")
        response_text = "抱歉，處理資料時出現問題。"
    except Exception as e:
        app.logger.error(f"處理消息時發生錯誤: {e}")
        response_text = "抱歉，目前無法處理您的請求。"

    # 回覆使用者
    message = TextSendMessage(text=response_text)
    line_bot_api.reply_message(event.reply_token, message)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
