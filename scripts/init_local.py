"""Generate local-only secrets without printing them or replacing existing .env files."""
from pathlib import Path
import secrets

root=Path(__file__).resolve().parents[1]
for folder in [root,root/'backend']:
    path=folder/'.env'
    if path.exists():
        print(f'Preserved {path}')
    else:
        path.write_text('JWT_SECRET='+secrets.token_urlsafe(48)+'\nPOSTGRES_PASSWORD='+secrets.token_urlsafe(24)+'\nMODEL_PROVIDER=deterministic\nCORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:5174\n')
        print(f'Created {path}; credentials were not printed')
