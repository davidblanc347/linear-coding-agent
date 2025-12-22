"""
Dockerization helper for ikario_body
===================================

Ce script crée les fichiers Docker nécessaires pour exécuter l'application
`generations/ikario_body` (frontend + serveur + base SQLite) dans Docker,
SANS modifier aucun fichier existant.

Il génère un fichier de composition :
  - docker-compose.ikario_body.yml  (à la racine du repo)

Ce fichier utilise l'image officielle Node et monte le code existant
ainsi que la base SQLite dans les conteneurs (mode développement).

Utilisation :
  1) Depuis la racine du repo :
       python dockerize_ikario_body.py
  2) Puis pour lancer l'appli dans Docker :
       docker compose -f docker-compose.ikario_body.yml up
     ou, selon votre installation :
       docker-compose -f docker-compose.ikario_body.yml up

  - Frontend accessible sur: http://localhost:3000
  - API backend (server) sur : http://localhost:3001
"""

from pathlib import Path


def generate_docker_compose(root: Path) -> None:
  """Génère le fichier docker-compose.ikario_body.yml sans toucher au code existant."""
  project_dir = root / "generations" / "ikario_body"

  if not project_dir.exists():
    raise SystemExit(f"Project directory not found: {project_dir}")

  compose_path = root / "docker-compose.ikario_body.yml"

  # On utilise les scripts npm déjà définis :
  # - frontend: npm run dev (Vite) en écoutant sur 0.0.0.0:3000 (dans le conteneur)
  # - server:   npm start dans ./server sur 3001 (dans le conteneur)
  #
  # Pour éviter les conflits de ports courants (3000/3001) sur la machine hôte,
  # on mappe vers des ports plus élevés côté host :
  #   - frontend : host 4300 -> container 3000
  #   - backend  : host 4301 -> container 3001
  #
  # Le volume ./generations/ikario_body est monté dans /app,
  # ce qui inclut aussi la base SQLite dans server/data/claude-clone.db.
  compose_content = f"""services:
  ikario_body_frontend:
    image: node:20
    working_dir: /app
    volumes:
      - ./generations/ikario_body:/app
      # Eviter de réutiliser les node_modules Windows dans le conteneur Linux
      - /app/node_modules
    command: ["sh", "-c", "npm install && npm run dev -- --host 0.0.0.0 --port 3000"]
    ports:
      - "4300:3000"
    environment:
      - NODE_ENV=development

  ikario_body_server:
    image: node:20
    working_dir: /app/server
    volumes:
      - ./generations/ikario_body:/app
      # Eviter de réutiliser les node_modules Windows dans le conteneur Linux
      - /app/server/node_modules
    command: ["sh", "-c", "npm install && npm start"]
    ports:
      - "4301:3001"
    environment:
      - NODE_ENV=development
    depends_on:
      - ikario_body_frontend

"""

  compose_path.write_text(compose_content, encoding="utf-8")
  print(f"Created {compose_path.relative_to(root)}")


def main() -> None:
  repo_root = Path(__file__).resolve().parent
  generate_docker_compose(repo_root)


if __name__ == "__main__":
  main()


