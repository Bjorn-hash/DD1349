from flask import Flask, render_template, request
import requests
import os
import difflib
from dotenv import load_dotenv
from datetime import datetime, timedelta
from geopy.distance import geodesic

# Load environment variables (make sure your .env file is in the same directory)
load_dotenv()
app = Flask(__name__)

#############################
# OpenRouter API settings
#############################
# The OpenRouter API key is now loaded from the environment.
OPENROUTER_API_TOKEN = os.getenv("OPENROUTER_API_TOKEN")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
openrouter_headers = {"Authorization": f"Bearer {OPENROUTER_API_TOKEN}"}

#############################
# Global Station Metadata Fetching
#############################
STATION_METADATA_URL = "https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/1.json"

def fetch_station_metadata():
    try:
        response = requests.get(STATION_METADATA_URL)
        response.raise_for_status()
        meta_data = response.json()
        return meta_data.get("station", [])
    except Exception as e:
        print("Failed to fetch SMHI station metadata:", e)
        return []

# Fetch metadata once at startup.
STATION_METADATA = fetch_station_metadata()
print(f"Fetched {len(STATION_METADATA)} stations from SMHI metadata.")

#############################
# Helper Function to Transform Timestamps
#############################
def transform_timestamps(data_list):
    """
    Convert each observation's 'date' (epoch in milliseconds) to a human‐readable date string (UTC)
    and add it as a new key "readable_date" to each record.
    """
    for record in data_list:
        record['readable_date'] = datetime.utcfromtimestamp(record['date'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
    return data_list

#############################
# Helper Function help correct city name spellings
#############################
def suggest_city_name(input_city, station_metadata):
    all_cities = [station.get("name", "") for station in station_metadata]
    suggestions = difflib.get_close_matches(input_city, all_cities, n=1, cutoff=0.6)
    return suggestions[0] if suggestions else None


#############################
# Routes
#############################
@app.route("/", methods=["GET", "POST"])
def index():
    coordinates = None
    selected_date = None
    station_info = None
    weather_data = None
    query_url = None
    error_message = None
    corrected_message = None
    llm_answer = None  # This will hold the summary from OpenRouter

    if request.method == "POST":
        city = request.form["city"]
        date_str = request.form["date"]

        try:
            selected_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            error_message = "Invalid date format."

        # SUGGESTED CITY MANAGEMENT:
        suggested_city = suggest_city_name(city, STATION_METADATA)
        corrected_message = None
        if suggested_city and suggested_city.lower() != city.lower():
            corrected_message = f"Sökningen korrigerades till '{suggested_city}'."
            city = suggested_city
        coordinates = geocode_city(city)
        if coordinates == (None, None):
            error_message = "Could not find that city"


        if city and selected_date:
            coordinates = geocode_city(city)

            if coordinates == (None, None):
                error_message = "Could not find that city"
            else:
                station_info = find_station_with_data(coordinates[0], coordinates[1], selected_date)
                if not station_info:
                    error_message = "No station found with data for the selected date."
                else:
                    station_id = station_info.get("id")
                    today = datetime.today()
                    if selected_date.date() >= today.date():
                        weather_data, query_url = get_smhi_temperature_data_forecast(coordinates[0], coordinates[1], selected_date)
                    else:
                        if selected_date.date() >= today.date() - timedelta(days=90):
                            period = "latest-month"
                        else:
                            period = "corrected-archive"
                        weather_data, query_url = get_smhi_temperature_data_historical(station_id, selected_date, period)
                    
                    if not weather_data or len(weather_data) == 0:
                        error_message = "No weather data available for that date."
                    else:
                        weather_data = transform_timestamps(weather_data)
                        llm_answer = get_llm_summary(city, selected_date, weather_data)
    
    return render_template("index.html",
                           coordinates=coordinates,
                           selected_date=selected_date,
                           station_info=station_info,
                           weather_data=weather_data,
                           query_url=query_url,
                           error_message=error_message,
                           corrected_message=corrected_message,
                           llm_answer=llm_answer)

#############################
# Helper Functions for Geocoding and Station Lookup
#############################
def geocode_city(city_name):
    api_key = os.getenv("OPENCAGE_API_KEY")
    url = f"https://api.opencagedata.com/geocode/v1/json?q={city_name}&key={api_key}"
    response = requests.get(url)
    data = response.json()
    print("OpenCage response:", data)




    if data.get("results"):
        lat = data["results"][0]["geometry"]["lat"]
        lon = data["results"][0]["geometry"]["lng"]
        return lat, lon
    return None, None

def find_station_with_data(user_lat, user_lon, date_obj):
    """
    Use the pre-fetched STATION_METADATA to select the nearest station that has data for the requested date.
    This function sorts stations by distance from the user and returns the first station whose metadata shows it
    has been updated on or after the requested date.
    """
    if not STATION_METADATA:
        return None

    def station_distance(station):
        return geodesic((user_lat, user_lon), (station["latitude"], station["longitude"])).km

    valid_stations = []
    for station in STATION_METADATA:
        updated_val = station.get("updated")
        if not updated_val:
            continue
        try:
            if isinstance(updated_val, str):
                update_dt = datetime.fromisoformat(updated_val.replace("Z", "+00:00"))
            else:
                update_dt = datetime.fromtimestamp(float(updated_val) / 1000.0)
            station["update_datetime"] = update_dt
            valid_stations.append(station)
        except Exception as e:
            print(f"Error parsing update for station {station.get('id')}: {e}")
            continue

    if not valid_stations:
        return None

    valid_stations.sort(key=station_distance)
    for station in valid_stations:
        if station.get("update_datetime") and station["update_datetime"] >= date_obj:
            print(f"Selected station {station['id']} (updated: {station['update_datetime']})")
            return station
    return valid_stations[0]

#############################
# Data Fetching Functions
#############################
def get_smhi_temperature_data_historical(station_id, date_obj, period_product):
    """
    Fetch historical weather data for a given station ID and date.
    period_product should be either "latest-month" or "corrected-archive".
    Returns a tuple: (day_data, query_url)
    """
    start = int(datetime(date_obj.year, date_obj.month, date_obj.day).timestamp() * 1000)
    end = int((datetime(date_obj.year, date_obj.month, date_obj.day) + timedelta(days=1)).timestamp() * 1000)
    
    if period_product == "latest-month":
        query_url = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/1/station/{station_id}/period/latest-months/data.json"
    elif period_product == "corrected-archive":
        query_url = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/1/station/{station_id}/period/corrected-archive.json"
    else:
        query_url = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/1/station/{station_id}/period/latest-months/data.json"
    
    response = requests.get(query_url)
    print(f"Historical SMHI API ({period_product}) status code:", response.status_code)
    print(f"Historical SMHI API ({period_product}) response (first 200 chars):", response.text[:200])
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        print("❌ Failed to decode historical SMHI JSON!")
        return ([], query_url)
    
    observations = data.get("value", [])
    day_data = [obs for obs in observations if start <= obs.get("date", 0) < end]
    return day_data, query_url

def get_smhi_temperature_data_forecast(lat, lon, date_obj):
    """
    Fetch forecast data using the SMHI forecast endpoint.
    Coordinates are rounded to three decimal places.
    Returns a tuple: (forecasts, query_url)
    """
    lon_str = f"{lon:.3f}"
    lat_str = f"{lat:.3f}"
    base_url = "https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2"
    url = f"{base_url}/geotype/point/lon/{lon_str}/lat/{lat_str}/data.json"
    response = requests.get(url)
    print("Forecast SMHI API status code:", response.status_code)
    print("Forecast SMHI API response (first 200 chars):", response.text[:200])
    try:
        data = response.json()
    except Exception as e:
        print("❌ Failed to decode forecast SMHI JSON!", e)
        return ([], url)
    forecasts = []
    for entry in data.get("timeSeries", []):
        valid_time = datetime.fromisoformat(entry["validTime"].replace("Z", "+00:00"))
        if valid_time.date() == date_obj.date():
            temp = None
            for param in entry.get("parameters", []):
                if param.get("name") == "t":
                    temp = param.get("values", [])[0]
                    break
            if temp is not None:
                forecasts.append({
                    "date": int(valid_time.timestamp() * 1000),
                    "value": temp
                })
    return forecasts, url

#############################
# LLM Summary Function using OpenRouter and Text-Generation Task
#############################
def get_llm_summary(city, date_obj, weather_data):
    """
    Build a prompt from the weather data summary and query OpenRouter's API using a text-generation task.
    """
    temperatures = []
    for record in weather_data:
        try:
            temperatures.append(float(record["value"]))
        except Exception as conv_e:
            print(f"Skipping invalid temperature value {record.get('value')}: {conv_e}")
    if temperatures:
        min_temp = min(temperatures)
        max_temp = max(temperatures)
        avg_temp = sum(temperatures) / len(temperatures)
        summary_line = f"Min: {min_temp}°C, Max: {max_temp}°C, Avg: {avg_temp:.1f}°C"
    else:
        summary_line = "No temperature data available."
    
    prompt = (
        f"Based on the weather data for {city} on {date_obj.strftime('%Y-%m-%d')}, which is summarized as: {summary_line}.\n\n"
        "Please provide a friendly summary of what the weather will be like and suggest some activities for that day in a conversational tone."
    )
    
    payload = {
        "model": "gpt-3.5-turbo",  # You may change this to your desired model as supported by OpenRouter.
        "messages": [
            {"role": "system", "content": "You are a helpful weather assistant."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 150
    }
    
    try:
        response = requests.post(OPENROUTER_API_URL, headers={"Authorization": f"Bearer {OPENROUTER_API_TOKEN}"}, json=payload, timeout=60)
        print("OpenRouter API status code:", response.status_code)
        print("OpenRouter raw response text:", response.text)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print("Error calling OpenRouter API:", e)
        return "Sorry, I couldn't generate a weather summary at this time."

if __name__ == "__main__":
    app.run(debug=True)
