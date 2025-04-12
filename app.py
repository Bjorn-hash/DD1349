from flask import Flask, render_template, request
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from geopy.distance import geodesic
import openai

load_dotenv()
app = Flask(__name__)

# Initialize the OpenAI client once using the API key from the environment.
openai.api_key = os.getenv("OPENAI_API_KEY")


@app.route("/", methods=["GET", "POST"])
def index():
    explanation = None
    if request.method == "POST":
        city = request.form["city"]
        date_str = request.form["date"]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")

        lat, lon = geocode_city(city)
        if not lat or not lon:
            explanation = "Could not find that city."
        else:
            station_id = find_nearest_smhi_station(lat, lon)
            if not station_id:
                explanation = "No nearby SMHI weather station found."
            else:
                smhi_data = get_smhi_temperature_data(station_id, date_obj)
                if not smhi_data:
                    explanation = "No weather data available for that date."
                else:
                    summary = "\n".join([
                        f"{datetime.fromtimestamp(d['date']/1000).strftime('%H:%M')} — {d['value']}°C"
                        for d in smhi_data
                    ])
                    # Create a prompt for ChatGPT
                    prompt = f"Summarize this weather data from {city} on {date_str}:\n{summary}"
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=300
                    )
                    explanation = response.choices[0].message.content

    return render_template("index.html", explanation=explanation)


# 1. Convert city name to coordinates using OpenCage
def geocode_city(city_name):
    api_key = os.getenv("OPENCAGE_API_KEY")
    url = f"https://api.opencagedata.com/geocode/v1/json?q={city_name}&key={api_key}"
    response = requests.get(url)
    data = response.json()

    print(data)
    print("HÄR_______________________________")

    if data["results"]:
        lat = data["results"][0]["geometry"]["lat"]
        lon = data["results"][0]["geometry"]["lng"]
        return lat, lon
    return None, None


# 2. Find the nearest SMHI weather station using version 1.0
def find_nearest_smhi_station(user_lat, user_lon):
    # Use version 1.0 endpoint to retrieve station metadata
    url = f"https://opendata-download-metobs.smhi.se/api/version/latest/parameter/1/station/{station_id}/period/latest-month/data.json"

    response = requests.get(url)
    data = response.json()

    nearest_station = None
    shortest_distance = float("inf")

    for station in data.get("station", []):
        station_lat = station["latitude"]
        station_lon = station["longitude"]
        dist = geodesic((user_lat, user_lon), (station_lat, station_lon)).km

        if dist < shortest_distance:
            shortest_distance = dist
            nearest_station = station

    if nearest_station:
        print("Nearest station ID:", nearest_station["id"])
        return nearest_station["id"]
    return None


# 3. Get temperature data from SMHI using version 1.0 observation endpoint
def get_smhi_temperature_data(station_id, date_obj):
    # Calculate the start and end of the day in milliseconds
    start = int(datetime(date_obj.year, date_obj.month, date_obj.day).timestamp() * 1000)
    end = int((datetime(date_obj.year, date_obj.month, date_obj.day) + timedelta(days=1)).timestamp() * 1000)

    # Use the SMHI version 1.0 endpoint in JSON format (without "/period/latest-day/")
    url = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/1/station/{station_id}.json"
    response = requests.get(url)

    print("SMHI API status code:", response.status_code)
    print("SMHI API response (first 200 chars):", response.text[:200])
    
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        print("❌ Failed to decode JSON from SMHI API!")
        return []
    
    # Extract observations from the "observations" key if present.
    observations = data.get("observations", {}).get("value", [])
    day_data = [obs for obs in observations if start <= obs["date"] < end]

    return day_data


if __name__ == "__main__":
    app.run(debug=True)