from flask import Flask, render_template, request
import requests
import openai
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)

# API keys
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

@app.route("/", methods=["GET", "POST"])
def index():
    explanation = None
    if request.method == "POST":
        city = request.form["city"]
        date_str = request.form["date"]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        timestamp = int(date_obj.timestamp())

        # Step 1: Get weather data
        weather_url = f"https://api.openweathermap.org/data/2.5/onecall/timemachine"
        lat, lon = get_coordinates(city)
        weather_response = requests.get(weather_url, params={
            "lat": lat,
            "lon": lon,
            "dt": timestamp,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric"
        })
        weather_data = weather_response.json()

        # Step 2: Format and send to OpenAI
        prompt = f"Explain this weather data for {city} on {date_str}:\n{weather_data}"
        ai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300
        )
        explanation = ai_response['choices'][0]['message']['content']

    return render_template("index.html", explanation=explanation)

def get_coordinates(city):
    geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OPENWEATHER_API_KEY}"
    response = requests.get(geo_url).json()
    return response[0]['lat'], response[0]['lon']

if __name__ == "__main__":
    app.run(debug=True)