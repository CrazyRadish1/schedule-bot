import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from dotenv import load_dotenv
from icalendar import Calendar

load_dotenv()
url = os.getenv('CALENDAR_URL')

classes = {'билингвизм', 'теоретический синтаксис', 'математическая теория грамматик', 'кпв невербальное',
           'типология грамматических категорий', 'статистические и корпусные методы',
           'английский язык в проф коммуникации', 'мфк', 'ридинг группа'}

tz = ZoneInfo('Europe/Moscow')
tmrw = date.today() + timedelta(days=1)
week_end = date.today() + timedelta(days=7)


def to_msk(dt):
    if isinstance(dt, datetime):
        return dt.astimezone(tz)
    return dt


def weather():
    access_key = os.getenv('YWEATHER_KEY')
    headers = {
        'X-Yandex-Weather-Key': access_key
    }
    response = requests.get('https://api.weather.yandex.ru/v2/forecast?lat=55.6781236&lon=37.5127061', headers=headers)
    data = response.json()
    today_str = date.today().isoformat()
    today_forecast = next(f for f in data["forecasts"] if f["date"] == today_str)
    hours = today_forecast["hours"]
    current_hour = datetime.now().hour
    hours = [h for h in hours if int(h["hour"]) >= current_hour]

    rain_hours = [h for h in hours if h["prec_type"] != 0]
    if rain_hours:
        has_rain = 1
        start = rain_hours[0]["hour"]
        end = rain_hours[-1]["hour"]
        rain_text = f"дождь с {start}:00 до {end}:00"
    else:
        has_rain = 0
        rain_text = "без дождя"

    max_wind = max(h["wind_gust"] for h in hours)

    avg_cloud = sum(h["cloudness"] for h in hours) / len(hours)
    if avg_cloud < 0.3:
        sky_text = "солнечно"
    elif avg_cloud < 0.7:
        sky_text = "переменная облачность"
    else:
        sky_text = "пасмурно"
    return has_rain, rain_text, max_wind, sky_text


response = requests.get(url)
text = response.text
calendar = Calendar.from_ical(text)

events = recurring_ical_events.of(calendar).at(date.today())
events = sorted(events, key=lambda e: e.get('DTSTART').dt)

message_lines = [f'{date.today():%d.%m (%a)}']
day_lessons = []

for event in events:
    summary = str(event.get('SUMMARY'))
    start = to_msk(event.get('DTSTART').dt)
    end = to_msk(event.get('DTEND').dt)

    if isinstance(start, datetime):
        message_lines.append(f'{start:%H:%M} - {end:%H:%M}: {summary}')
    else:
        message_lines.append(f'Весь день: {summary}')

    if summary.lower() in classes:
        day_lessons.append(summary.lower())

lesson_events = [e for e in events if str(e.get('SUMMARY')).lower() in classes]
if lesson_events:
    first_event = min(lesson_events, key=lambda e: e.get('DTSTART').dt)
    start = to_msk(first_event.get('DTSTART').dt)
    minutes_before = 50 if (start.hour == 9 and start.minute == 0) else 40
    out = start - timedelta(minutes=minutes_before)
    message_lines.append(f'первая пара в {start:%H:%M}, время выхода: {out:%H:%M}')

message_lines.append('')

has_rain, rain_text, max_wind, sky_text = weather()
message_lines.append(f'погода: {sky_text}, ветер до {max_wind:.0f} м/с, {rain_text}')
message_lines.append('')

def suggest_items(has_rain):
    items = []
    shopper = None

    if has_rain:
        items.append('зонт')

    if 'статистические и корпусные методы' in day_lessons:
        items.append('ноутбук')
        shopper = 'рюкзак'
    elif has_rain:
        shopper = 'белый шоппер'
    else:
        shopper = 'серый/белый шоппер'

    if len(day_lessons) > 1:
        items.append('зарядка')
    if 'мфк' in day_lessons or 'математическая теория грамматик' in day_lessons:
        items.append('блокнот')
        items.append('ручка')
    if 'теоретический синтаксис' in day_lessons and 'ручка' not in items:
        items.append('ручка')

    return items, shopper


items, shopper = suggest_items(has_rain)
message_lines.append('взять: ' + ', '.join(items))
message_lines.append('')
if shopper:
    message_lines.append(f'рекомендуется: {shopper}')

final_text = '\n'.join(message_lines)
print(final_text)


def send_telegram(text):
    token = os.getenv('TELEGRAM_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    requests.post(
        f'https://api.telegram.org/bot{token}/sendMessage',
        data={'chat_id': chat_id, 'text': text}
    )


send_telegram(final_text)
