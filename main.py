import threading

from flask import Flask

app = Flask(__name__)

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from dotenv import load_dotenv
from icalendar import Calendar


def run_bot():
    load_dotenv()
    url = os.getenv('CALENDAR_URL')

    classes = {
        'билингвизм',
        'теоретический синтаксис',
        'математическая теория грамматик',
        'кпв невербальное',
        'типология грамматических категорий',
        'статистические и корпусные методы',
        'английский язык в проф коммуникации',
        'мфк',
        'ридинг группа'
    }

    tz = ZoneInfo('Europe/Moscow')

    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)

    week_end = today + timedelta(days=7)

    def to_msk(dt):
        if isinstance(dt, datetime):
            return dt.astimezone(tz)
        return dt

    def weather():
        access_key = os.getenv('YWEATHER_KEY')
        headers = {
            'X-Yandex-Weather-Key': access_key
        }

        response = requests.get(
            'https://api.weather.yandex.ru/v2/forecast?lat=55.6781236&lon=37.5127061',
            headers=headers
        )

        data = response.json()

        tomorrow_str = tomorrow.isoformat()

        tomorrow_forecast = next(
            f for f in data["forecasts"]
            if f["date"] == tomorrow_str
        )

        hours = tomorrow_forecast["hours"]
        parts = tomorrow_forecast["parts"]
        temp_morning = round(parts["morning"]["temp_avg"])
        temp_day = round(parts["day"]["temp_avg"])
        temp_evening = round(parts["evening"]["temp_avg"])

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

        avg_cloud = sum(
            h["cloudness"] for h in hours
        ) / len(hours)

        if avg_cloud < 0.3:
            sky_text = "солнечно"
        elif avg_cloud < 0.7:
            sky_text = "переменная облачность"
        else:
            sky_text = "пасмурно"

        return has_rain, rain_text, max_wind, sky_text, temp_morning, temp_day, temp_evening

    response = requests.get(url)
    text = response.text
    calendar = Calendar.from_ical(text)

    events = recurring_ical_events.of(calendar).at(tomorrow)
    events = sorted(events, key=lambda e: e.get('DTSTART').dt)

    message_lines = [f'{tomorrow:%d.%m (%a)}']

    day_lessons = []

    for event in events:
        summary = str(event.get('SUMMARY'))
        start = to_msk(event.get('DTSTART').dt)
        end = to_msk(event.get('DTEND').dt)

        if isinstance(start, datetime):
            message_lines.append(
                f'{start:%H:%M} - {end:%H:%M}: {summary}'
            )
        else:
            message_lines.append(
                f'Весь день: {summary}'
            )

        if summary.lower() in classes:
            day_lessons.append(summary.lower())

    lesson_events = [
        e for e in events
        if str(e.get('SUMMARY')).lower() in classes
    ]

    if lesson_events:
        first_event = min(
            lesson_events,
            key=lambda e: e.get('DTSTART').dt
        )

        start = to_msk(first_event.get('DTSTART').dt)

        minutes_before = (
            50
            if (start.hour == 9 and start.minute == 0)
            else 40
        )

        out = start - timedelta(minutes=minutes_before)
        standup = out - timedelta(minutes=45)
        wakeup = standup - timedelta(minutes=30)

        message_lines.append(
            f'первая пара в {start:%H:%M}, проснуться: {wakeup:%H:%M}, встать: {standup:%H:%M}, время выхода: {out:%H:%M}'
        )

    message_lines.append('')

    has_rain, rain_text, max_wind, sky_text, temp_morning, temp_day, temp_evening = weather()

    message_lines.append(
        f'погода: {sky_text}, ветер до {max_wind:.0f} м/с, {rain_text}'
    )
    message_lines.append(
        f'температура: утром {temp_morning}°, днём {temp_day}°, вечером {temp_evening}°'
    )

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

        if (
                'мфк' in day_lessons
                or 'математическая теория грамматик' in day_lessons
        ):
            items.append('блокнот')
            items.append('ручка')

        if (
                'теоретический синтаксис' in day_lessons
                and 'ручка' not in items
        ):
            items.append('ручка')

        return items, shopper

    items, shopper = suggest_items(has_rain)

    message_lines.append(
        'взять: ' + ', '.join(items)
    )

    message_lines.append('')

    if shopper:
        message_lines.append(
            f'рекомендуется: {shopper}'
        )

    final_text = '\n'.join(message_lines)

    print(final_text)

    def send_telegram(text):
        token = os.getenv('TELEGRAM_TOKEN')
        chat_ids = os.getenv('TELEGRAM_CHAT_IDs').split(',')

        for chat_id in chat_ids:
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                data={
                    'chat_id': chat_id.strip(),
                    'text': text
                }
            )


send_telegram(final_text)


@app.route('/')
def home():
    return 'Bot is running'


@app.route('/run')
def run():
    print('RUN ENDPOINT CALLED')
    threading.Thread(target=run_bot).start()
    return 'Bot started'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
