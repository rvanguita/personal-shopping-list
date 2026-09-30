"""Leitura de variáveis de ambiente tolerante a valores entre aspas."""

import os

import shopping_list.config  # noqa: F401  (carrega o .env)


def getenv(name: str, default: str | None = None) -> str | None:
    """Como `os.getenv`, mas remove aspas simples/duplas ao redor do valor.

    O `docker compose` (`env_file`) pode repassar `VAR="valor"` com as aspas
    literais, o que quebra host/usuário/senha.
    """
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value
