# Architecture pour Weaviate distant (Synology/VPS)

## Votre cas d'usage

**Situation** : Application LLM (local ou cloud) → Weaviate (Synology ou VPS distant)

**Besoins** :
- ✅ Fiabilité maximale
- ✅ Sécurité (données privées)
- ✅ Performance acceptable
- ✅ Maintenance simple

---

## 🏆 Option recommandée : API REST + Tunnel sécurisé

### Architecture globale

```
┌──────────────────────────────────────────────────────────────┐
│                    Application LLM                            │
│  (Claude API, OpenAI, Ollama local, etc.)                    │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│              API REST Custom (Flask/FastAPI)                  │
│  - Authentification JWT/API Key                              │
│  - Rate limiting                                              │
│  - Logging                                                    │
│  - HTTPS (Let's Encrypt)                                     │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼ (réseau privé ou VPN)
┌──────────────────────────────────────────────────────────────┐
│         Synology NAS / VPS                                    │
│  ┌────────────────────────────────────────────────────┐      │
│  │  Docker Compose                                     │      │
│  │  ┌──────────────────┐  ┌─────────────────────┐     │      │
│  │  │ Weaviate :8080   │  │ text2vec-transformers│    │      │
│  │  └──────────────────┘  └─────────────────────┘     │      │
│  └────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

### Pourquoi cette option ?

✅ **Fiabilité maximale** (5/5)
- HTTP/REST = protocole standard, éprouvé
- Retry automatique facile
- Gestion d'erreur claire

✅ **Sécurité** (5/5)
- HTTPS obligatoire
- Authentification par API key
- IP whitelisting possible
- Logs d'audit

✅ **Performance** (4/5)
- Latence réseau inévitable
- Compression gzip possible
- Cache Redis optionnel

✅ **Maintenance** (5/5)
- Code simple (Flask/FastAPI)
- Monitoring facile
- Déploiement standard

---

## Comparaison des 4 options

### Option 1 : API REST Custom (⭐ RECOMMANDÉ)

**Architecture** : App → API REST → Weaviate

**Code exemple** :

```python
# api_server.py (déployé sur VPS/Synology)
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
import weaviate

app = FastAPI()
api_key_header = APIKeyHeader(name="X-API-Key")

# Connect to Weaviate (local on same machine)
client = weaviate.connect_to_local()

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

@app.post("/search")
async def search_chunks(
    query: str,
    limit: int = 10,
    api_key: str = Security(verify_api_key)
):
    collection = client.collections.get("Chunk")
    result = collection.query.near_text(
        query=query,
        limit=limit
    )
    return {"results": [obj.properties for obj in result.objects]}

@app.post("/insert_pdf")
async def insert_pdf(
    pdf_path: str,
    api_key: str = Security(verify_api_key)
):
    # Appeler le pipeline library_rag
    from utils.pdf_pipeline import process_pdf
    result = process_pdf(Path(pdf_path))
    return result
```

**Déploiement** :

```bash
# Sur VPS/Synology
docker-compose up -d weaviate text2vec
uvicorn api_server:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

**Avantages** :
- ✅ Contrôle total sur l'API
- ✅ Facile à sécuriser (HTTPS + API key)
- ✅ Peut wrapper tout le pipeline library_rag
- ✅ Monitoring et logging faciles

**Inconvénients** :
- ⚠️ Code custom à maintenir
- ⚠️ Besoin d'un serveur web (nginx/uvicorn)

---

### Option 2 : Accès direct Weaviate via VPN

**Architecture** : App → VPN → Weaviate:8080

**Configuration** :

```bash
# Sur Synology : activer VPN Server (OpenVPN/WireGuard)
# Sur client : se connecter au VPN
# Accès direct à http://192.168.x.x:8080 (IP privée Synology)
```

**Code client** :

```python
# Dans votre app LLM
import weaviate

# Via VPN, IP privée Synology
client = weaviate.connect_to_custom(
    http_host="192.168.1.100",
    http_port=8080,
    http_secure=False,  # En VPN, pas besoin HTTPS
    grpc_host="192.168.1.100",
    grpc_port=50051,
)

# Utilisation directe
collection = client.collections.get("Chunk")
result = collection.query.near_text(query="justice")
```

**Avantages** :
- ✅ Très simple (pas de code custom)
- ✅ Sécurité via VPN
- ✅ Utilise Weaviate client Python directement

**Inconvénients** :
- ⚠️ VPN doit être actif en permanence
- ⚠️ Latence VPN
- ⚠️ Pas de couche d'abstraction (app doit connaître Weaviate)

---

### Option 3 : MCP Server HTTP sur VPS

**Architecture** : App → MCP HTTP → Weaviate

**Problème** : FastMCP SSE ne fonctionne pas bien en production (comme on l'a vu)

**Solution** : Wrapper custom MCP over HTTP

```python
# mcp_http_wrapper.py (sur VPS)
from fastapi import FastAPI
from mcp_tools import parse_pdf_handler, search_chunks_handler
from pydantic import BaseModel

app = FastAPI()

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

@app.post("/mcp/search_chunks")
async def mcp_search(req: SearchRequest):
    # Appeler directement le handler MCP
    input_data = SearchChunksInput(query=req.query, limit=req.limit)
    result = await search_chunks_handler(input_data)
    return result.model_dump()
```

**Avantages** :
- ✅ Réutilise le code MCP existant
- ✅ HTTP standard

**Inconvénients** :
- ⚠️ MCP stdio ne peut pas être utilisé
- ⚠️ Besoin d'un wrapper HTTP custom de toute façon
- ⚠️ Équivalent à l'option 1 en plus complexe

**Verdict** : Option 1 (API REST pure) est meilleure

---

### Option 4 : Tunnel SSH + Port forwarding

**Architecture** : App → SSH tunnel → localhost:8080 (Weaviate distant)

**Configuration** :

```bash
# Sur votre machine locale
ssh -L 8080:localhost:8080 user@synology-ip

# Weaviate distant est maintenant accessible sur localhost:8080
```

**Code** :

```python
# Dans votre app (pense que Weaviate est local)
client = weaviate.connect_to_local()  # Va sur localhost:8080 = tunnel SSH
```

**Avantages** :
- ✅ Sécurité SSH
- ✅ Simple à configurer
- ✅ Pas de code custom

**Inconvénients** :
- ⚠️ Tunnel doit rester ouvert
- ⚠️ Pas adapté pour une app cloud
- ⚠️ Latence SSH

---

## 🎯 Recommandations selon votre cas

### Cas 1 : Application locale (votre PC) → Weaviate Synology/VPS

**Recommandation** : **VPN + Accès direct Weaviate** (Option 2)

**Pourquoi** :
- Simple à configurer sur Synology (VPN Server intégré)
- Pas de code custom
- Sécurité via VPN
- Performance acceptable en réseau local/VPN

**Setup** :

1. Synology : Activer VPN Server (OpenVPN)
2. Client : Se connecter au VPN
3. Python : `weaviate.connect_to_custom(http_host="192.168.x.x", ...)`

---

### Cas 2 : Application cloud (serveur distant) → Weaviate Synology/VPS

**Recommandation** : **API REST Custom** (Option 1)

**Pourquoi** :
- Pas de VPN nécessaire
- HTTPS public avec Let's Encrypt
- Contrôle d'accès par API key
- Rate limiting
- Monitoring

**Setup** :

1. VPS/Synology : Docker Compose (Weaviate + API REST)
2. Domaine : api.monrag.com → VPS IP
3. Let's Encrypt : HTTPS automatique
4. App cloud : Appelle `https://api.monrag.com/search?api_key=xxx`

---

### Cas 3 : Développement local temporaire → Weaviate distant

**Recommandation** : **Tunnel SSH** (Option 4)

**Pourquoi** :
- Setup en 1 ligne
- Aucune config permanente
- Parfait pour le dev/debug

**Setup** :

```bash
ssh -L 8080:localhost:8080 user@vps
# Weaviate distant accessible sur localhost:8080
```

---

## 🔧 Déploiement recommandé pour VPS

### Stack complète

```yaml
# docker-compose.yml (sur VPS)
version: '3.8'

services:
  # Weaviate + embeddings
  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.34.4
    ports:
      - "127.0.0.1:8080:8080"  # Uniquement localhost (sécurité)
    environment:
      AUTHENTICATION_APIKEY_ENABLED: "true"
      AUTHENTICATION_APIKEY_ALLOWED_KEYS: "my-secret-key"
      # ... autres configs
    volumes:
      - weaviate_data:/var/lib/weaviate

  text2vec-transformers:
    image: cr.weaviate.io/semitechnologies/transformers-inference:baai-bge-m3-onnx-latest
    # ... config

  # API REST custom
  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      WEAVIATE_URL: http://weaviate:8080
      API_KEY: ${API_KEY}
      MISTRAL_API_KEY: ${MISTRAL_API_KEY}
    depends_on:
      - weaviate
    restart: always

  # NGINX reverse proxy + HTTPS
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - /etc/letsencrypt:/etc/letsencrypt
    depends_on:
      - api

volumes:
  weaviate_data:
```

### NGINX config

```nginx
# nginx.conf
server {
    listen 443 ssl;
    server_name api.monrag.com;

    ssl_certificate /etc/letsencrypt/live/api.monrag.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.monrag.com/privkey.pem;

    location / {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Rate limiting
        limit_req zone=api_limit burst=10 nodelay;
    }
}
```

---

## 📊 Comparaison finale

| Critère | VPN + Direct | API REST | Tunnel SSH | MCP HTTP |
|---------|--------------|----------|------------|----------|
| **Fiabilité** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **Sécurité** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Simplicité** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Performance** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Maintenance** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Production** | ✅ Oui | ✅ Oui | ❌ Non | ⚠️ Possible |

---

## 💡 Ma recommandation finale

### Pour Synology (usage personnel/équipe)
**VPN + Accès direct Weaviate** (Option 2)
- Synology a un excellent VPN Server intégré
- Sécurité maximale
- Simple à maintenir

### Pour VPS (usage production/public)
**API REST Custom** (Option 1)
- Contrôle total
- HTTPS public
- Scalable
- Monitoring complet

---

## 🚀 Prochaine étape recommandée

Voulez-vous que je crée :

1. **Le code de l'API REST** (Flask/FastAPI) avec auth + rate limiting ?
2. **Le docker-compose VPS complet** avec nginx + Let's Encrypt ?
3. **Le guide d'installation Synology VPN** + config client ?

Dites-moi votre cas d'usage exact et je vous prépare la solution complète ! 🎯
