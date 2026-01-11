import requests

BASE = "https://yj.970108.xyz"
TOKEN = requests.post(f"{BASE}/api/auth/login", json={"username":"admin","password":"wu123456"}).json()["token"]
H = {"Authorization": f"Bearer {TOKEN}"}

result = requests.post(f"{BASE}/api/emails/get_code", headers=H, json={
    "email": "hpgumvqbxlfi0o@outlook.com",
    "timeout": 10
}).json()

print(result)
