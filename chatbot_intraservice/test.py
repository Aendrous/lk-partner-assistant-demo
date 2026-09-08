import requests
import json

url = "https://llm.iek.local/v1/chat/completions"
headers = {
    "Authorization": "Bearer sk-DEAQ5ruqqoGZQzuFyZ3ymw",
    "Content-Type": "application/json"
}
data = {
    "model": "iek/gpt-oss-120b",
    "messages": [{"role": "user", "content": "Привет, как дела?"}],
    "max_tokens": 100
}

response = requests.post(url, headers=headers, json=data, timeout=60)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")