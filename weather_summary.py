import json
from collections import Counter, defaultdict, deque, namedtuple
from pathlib import Path

import requests


SOURCE_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=43.65&longitude=79.38"
    "&hourly=temperature_2m,precipitation"
    "&past_days=7&forecast_days=0"
    "&timezone=America/Toronto"
)

OUTPUT_FILE = Path("weather_summary.json")


# namedtuple gives each valid weather record a clear structure.
WeatherRecord = namedtuple(
    "WeatherRecord",
    ["time", "temperature", "precipitation"]
)


def download_data():
    """Download weather data and return the JSON response."""
    try:
        response = requests.get(SOURCE_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"Download failed: {exc}")
        return None


def process_data(data):
    """Validate records and create several summaries."""

    if not isinstance(data, dict):
        print("Download failed: response was not a JSON object.")
        return None

    hourly = data.get("hourly")

    if not isinstance(hourly, dict):
        print("Download failed: hourly data is missing or malformed.")
        return None

    times = hourly.get("time")
    temperatures = hourly.get("temperature_2m")
    precipitation = hourly.get("precipitation")

    if not all(isinstance(value, list)
               for value in (times, temperatures, precipitation)):
        print("Download failed: hourly fields are malformed.")
        return None

    # We expect many hourly records. The API normally returns 168
    # records for seven past days.
    records = []
    invalid_records = 0

    for time_value, temp_value, rain_value in zip(
        times, temperatures, precipitation
    ):
        # Do not silently treat bad values as zero.
        if (
            not isinstance(time_value, str)
            or not isinstance(temp_value, (int, float))
            or isinstance(temp_value, bool)
            or not isinstance(rain_value, (int, float))
            or isinstance(rain_value, bool)
        ):
            invalid_records += 1
            continue

        records.append(
            WeatherRecord(
                time=time_value,
                temperature=float(temp_value),
                precipitation=float(rain_value),
            )
        )

    if len(records) < 50:
        print(
            f"Download failed: only {len(records)} valid records were found; "
            "at least 50 are required."
        )
        return None

    # ------------------------------------------------------------
    # Aggregation 1: group records by date using defaultdict.
    # ------------------------------------------------------------
    daily_records = defaultdict(list)

    for record in records:
        date = record.time.split("T")[0]
        daily_records[date].append(record)

    daily_summary = {}

    for date, day_records in daily_records.items():
        daily_summary[date] = {
            "record_count": len(day_records),
            "average_temperature": round(
                sum(r.temperature for r in day_records) / len(day_records),
                2,
            ),
            "total_precipitation": round(
                sum(r.precipitation for r in day_records),
                2,
            ),
        }

    # ------------------------------------------------------------
    # Aggregation 2: count temperature categories using Counter.
    # ------------------------------------------------------------
    temperature_categories = Counter()

    for record in records:
        if record.temperature < 0:
            category = "below_freezing"
        elif record.temperature < 10:
            category = "cool"
        elif record.temperature < 20:
            category = "mild"
        else:
            category = "warm"

        temperature_categories[category] += 1

    # ------------------------------------------------------------
    # deque: keep the most recent 24 temperatures.
    # ------------------------------------------------------------
    recent_temperatures = deque(
        (record.temperature for record in records),
        maxlen=24,
    )

    # ------------------------------------------------------------
    # Comprehension: create a list of daily dates.
    # ------------------------------------------------------------
    dates_processed = [
        record.time.split("T")[0]
        for record in records
    ]

    # Remove duplicates while preserving order.
    unique_dates = list(dict.fromkeys(dates_processed))

    summary = {
        "source_url": SOURCE_URL,
        "records_processed": len(records),
        "invalid_records_skipped": invalid_records,
        "days_processed": len(unique_dates),

        "daily_summary": daily_summary,

        "temperature_categories": dict(temperature_categories),

        "overall": {
            "average_temperature": round(
                sum(record.temperature for record in records)
                / len(records),
                2,
            ),
            "total_precipitation": round(
                sum(record.precipitation for record in records),
                2,
            ),
            "maximum_temperature": max(
                record.temperature for record in records
            ),
            "minimum_temperature": min(
                record.temperature for record in records
            ),
        },

        "most_recent_24_temperatures": list(recent_temperatures),
    }

    return summary


def main():
    data = download_data()

    if data is None:
        return

    summary = process_data(data)

    if summary is None:
        return

    # pathlib is used to write the JSON output.
    try:
        OUTPUT_FILE.write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"Could not write output file: {exc}")
        return

    print(
        f"Success: processed {summary['records_processed']} valid "
        f"records and wrote {OUTPUT_FILE}."
    )


if __name__ == "__main__":
    main()
