"""Caminhos do projeto e carga do `.env`, ancorados na raiz do repositório.

Cada app roda a partir da sua própria pasta (`app/<app>/`), então nada aqui
depende do diretório corrente.
"""

from pathlib import Path

import dotenv

PROJECT_ROOT = (
    Path(__file__).resolve().parents[2]
)  # src/shopping_list/config.py -> raiz
DOCS_DIR = PROJECT_ROOT / "docs"
QUERY_DIR = Path(__file__).parent / "query"
PROMPT_PATH = DOCS_DIR / "template" / "prompt.md"
RESPONSE_PATH = DOCS_DIR / "template" / "response.json"

dotenv.load_dotenv(PROJECT_ROOT / ".env")
