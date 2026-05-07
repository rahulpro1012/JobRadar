import requests, os
from dotenv import load_dotenv
load_dotenv()

key = os.environ.get('JOOBLE_API_KEY')

queries = [
    {"keywords": "Java Developer", "location": "Pune, India"},
    {"keywords": "Java Developer", "location": "India"},
    {"keywords": "Software Engineer", "location": ""},
    {"keywords": "Spring Boot", "location": "India"},
    {"keywords": "Java", "location": "Mumbai"},
]

for q in queries:
    r = requests.post(
        f'https://jooble.org/api/{key}',
        json=q,
        verify=False,
        timeout=15
    )
    data = r.json()
    count = data.get("totalCount", 0)
    jobs = data.get("jobs", [])
    print(f'"{q["keywords"]}" + "{q["location"]}" → {count} total, {len(jobs)} returned')
    if jobs:
        print(f'  First: {jobs[0].get("title", "")[:60]}')