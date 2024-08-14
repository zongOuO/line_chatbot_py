from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
from groq import Groq
from firebase import firebase
import requests
from io import StringIO
from datetime import datetime



app = Flask(__name__)

# Initialize LINE Bot API and Webhook Handler
line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])
firebase_url = os.getenv('FIREBASE_URL')
weather_api_key = os.getenv('WEATHER_API_KEY')


# Initialize Groq Client
groq_client = Groq(api_key=os.environ['GROQ_API_KEY'])


locationlist = ['宜蘭縣', '花蓮縣', '臺東縣', '澎湖縣', '金門縣', '連江縣', '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市', '基隆市', '新竹縣', '新竹市', '苗栗縣', '彰化縣', '南投縣', '雲林縣', '嘉義縣', '嘉義市', '屏東縣']
location_map = {
    '宜蘭': locationlist[0], '宜蘭縣': locationlist[0],
    '花蓮': locationlist[1], '花蓮縣': locationlist[1],
    '台東': locationlist[2], '臺東': locationlist[2], '台東縣': locationlist[2], '臺東縣': locationlist[2],
    '澎湖': locationlist[3], '澎湖縣': locationlist[3],
    '金門': locationlist[4], '金門縣': locationlist[4],
    '連江': locationlist[5], '連江縣': locationlist[5],
    '台北': locationlist[6], '台北市': locationlist[6], '臺北市': locationlist[6],
    '新北': locationlist[7], '新北市': locationlist[7],
    '桃園': locationlist[8], '桃園市': locationlist[8],
    '台中': locationlist[9], '台中市': locationlist[9], '臺中市': locationlist[9],
    '台南': locationlist[10], '台南市': locationlist[10], '臺南市': locationlist[10],
    '高雄': locationlist[11], '高雄市': locationlist[11],
    '基隆': locationlist[12], '基隆市': locationlist[12],
    '新竹': locationlist[13], '新竹縣': locationlist[13],
    '新竹市': locationlist[14],
    '苗栗': locationlist[15], '苗栗縣': locationlist[15],
    '彰化': locationlist[16], '彰化縣': locationlist[16],
    '南投': locationlist[17], '南投縣': locationlist[17],
    '雲林': locationlist[18], '雲林縣': locationlist[18],
    '嘉義': locationlist[19], '嘉義縣': locationlist[19],
    '嘉義市': locationlist[20],
    '屏東': locationlist[21], '屏東縣': locationlist[21],
    }

def parse_weather_data(data):
    output = StringIO()
    location = data['records']['location'][0]
    location_name = location['locationName']
    weather_elements = location['weatherElement']

    weather_info = {}

    element_names = {
        'Wx': '天氣現象',
        'MaxT': '最高溫度',
        'MinT': '最低溫度',
        'CI': '舒適度',
        'PoP': '降雨機率'
    }

    for element in weather_elements:
        element_name = element['elementName']
        for time_slot in element['time']:
            start_time = datetime.strptime(time_slot['startTime'], "%Y-%m-%d %H:%M:%S")
            end_time = datetime.strptime(time_slot['endTime'], "%Y-%m-%d %H:%M:%S")
            time_key = f"{start_time.strftime('%Y-%m-%d %H:%M')} 至 {end_time.strftime('%Y-%m-%d %H:%M')}"
            
            if time_key not in weather_info:
                weather_info[time_key] = {}
            
            if 'parameter' in time_slot:
                param = time_slot['parameter']
                if 'parameterName' in param:
                    value = param['parameterName']
                    if element_name in ['MaxT', 'MinT']:
                        value += '°C'
                    elif element_name == 'PoP':
                        value += '%'
                    weather_info[time_key][element_names.get(element_name, element_name)] = value

    return output.getvalue()

def weather(user_location):
    if user_location in location_map:
        city = location_map[user_location]
        api_url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={weather_api_key}&locationName={city}'
        try:
            response = requests.get(api_url)
            response.raise_for_status()  # 這會引發 HTTPError，讓你可以處理響應錯誤
            data = response.json()
            # 確保 data 包含預期的字段
            return parse_weather_data(data)
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Weather API request error: {e}")
            return None
    else:
        app.logger.warning("Unsupported location")
        return None



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
            if "查詢天氣" in user_message or "天氣查詢" in user_message:
                matched_locations = None
                # 遍歷 location_map 辭典的所有鍵
                for location in location_map.keys():
                    if location in user_message:
                        matched_locations = location
                        break
                
                if matched_locations:
                    weather_info = weather(matched_locations)
                    user_message = str(weather_info) + user_message
                else:
                    user_message = "未找到匹配的地點，無法查詢天氣。" + user_message

            # 添加用戶消息到歷史記錄
            chat_history.append({"role": "user", "content": user_message})
            
            # 準備發送給 Groq 的消息列表
            messages_for_groq = [
                {"role": "system", "content": "你只會繁體中文，回答任何問題時，都會使用繁體中文回答，口氣要親切。"}]
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
