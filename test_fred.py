from fredapi import Fred
import os
from dotenv import load_dotenv

load_dotenv()
FRED_KEY = os.getenv("FRED_API_KEY")

print(f"Key loaded: {'yes, starts with ' + FRED_KEY[:5] if FRED_KEY else 'NO KEY FOUND'}")

fred = Fred(api_key=FRED_KEY)
data = fred.get_series("FEDFUNDS")
print(data.tail())