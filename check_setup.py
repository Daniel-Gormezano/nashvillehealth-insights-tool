from pathlib import Path
import requests
from src.data_service import HealthDataRepository
ROOT=Path(__file__).resolve().parent
required=[ROOT/'app.py',ROOT/'data/health_data.csv',ROOT/'data/indicator_metadata.csv',ROOT/'assets/brand.css',ROOT/'assets/nashvillehealth_logo.png',ROOT/'assets/tennessee_duotone.png']
missing=[p.name for p in required if not p.exists()]
if missing:raise SystemExit('Missing files: '+', '.join(missing))
try:
 r=requests.get('http://localhost:11434/api/tags',timeout=3);r.raise_for_status();models=[x.get('name','') for x in r.json().get('models',[])];print('Ollama connected.' if any(x.startswith('llama3.2') for x in models) else 'Ollama connected, but llama3.2 was not found.')
except Exception:print('Ollama is not reachable. The app will use verified-data fallback mode.')
repo=HealthDataRepository(ROOT/'data/health_data.csv',ROOT/'data/indicator_metadata.csv');print(f'Data ready: {len(repo.indicator_names)} indicators, {len(repo.city_names)} cities.')
