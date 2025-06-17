from binance.client import Client
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

client = Client(API_KEY, API_SECRET)
try:
    print(client.get_account())
except Exception as e:
    print(f"Erro: {e}")
