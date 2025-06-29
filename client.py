import requests
import json

if __name__ == "__main__":
    # Testing client
    stream = False

    r = requests.post("http://localhost:48001/api/chat", json={
        "model": "qwen3:1.7b",
        "messages": [
            {"role": "user", "content": "Use tools to tell hello to Francis"}
        ],
        "stream": stream,
        "options": {
            "temperature": 0
        }
    }, stream=stream)

    if stream:
        for line in r.iter_lines():
          print(f"{line.decode('utf8')}")
    else:
        print(f"{json.dumps(r.json(), indent=2)}")