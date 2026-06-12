import psycopg2
from app.config import env


def conectar_banco():
    return psycopg2.connect(
        host=env("DB_HOST"),
        port=env("DB_PORT"),
        database=env("DB_BANCO"),
        user=env("DB_USER"),
        password=env("DB_SENHA")
    )