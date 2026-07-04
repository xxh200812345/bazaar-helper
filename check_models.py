import urllib.request
import json
import os

key_path = r"C:\Users\xxh20\AppData\Local\BazaarHelper\runtime\ai_api_key.txt"
with open(key_path, "r") as f:
    key = f.read().strip()

url = "https://generativelanguage.googleapis.com/v1beta/openai/models"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
try:
    response = urllib.request.urlopen(req).read()
    data = json.loads(response)
    for model in data.get("data", []):
        print(model.get("id"))
except Exception as e:
    print(e)
