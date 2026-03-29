import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()
conn = psycopg2.connect(
    os.getenv('DATABASE_URL'),
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5,
)
cur = conn.cursor()
cur.execute('TRUNCATE TABLE pokemon_moves, evolutions, moves, pokemon_embeddings, pokemon CASCADE;')
conn.commit()
cur.close()
conn.close()
print('Done — all tables cleared.')