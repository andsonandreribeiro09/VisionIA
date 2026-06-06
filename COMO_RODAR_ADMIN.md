# VisionAI Admin

O Admin e o painel central para controlar lojas, licencas e vencimentos.

## Rodar local

```powershell
.\iniciar_admin_local.ps1
```

Acesse:

```text
http://localhost:5002/admin
```

Usuario padrao:

```text
admin
```

Senha padrao:

```text
visionai-admin
```

Em producao, troque a senha no `.env.local` ou nas variaveis do Render:

```text
VISIONAI_ADMIN_USER=admin
VISIONAI_ADMIN_PASSWORD=uma-senha-forte
```

## Render

Crie um novo Web Service usando:

```text
Dockerfile.admin
VISIONAI_APP=admin
DATABASE_URL=postgresql://...
SECRET_KEY=...
VISIONAI_ADMIN_PASSWORD=uma-senha-forte
```

URL sugerida:

```text
https://admin.visioniaotica.com.br
```

## API de licenca

Endpoint:

```text
POST /api/licenca/verificar
```

Exemplo:

```json
{
  "store_id": "detecta-vision-osasco-001",
  "license_key": "copie-a-chave-gerada-no-admin",
  "machine_id": "PC-LOJA-001",
  "app_version": "1.0.0",
  "medicoes_hoje": 12,
  "banco_status": "ok"
}
```

Resposta ativa:

```json
{
  "status": "ativo",
  "captura_liberada": true,
  "dias_restantes": 30
}
```

Resposta vencida ou suspensa:

```json
{
  "status": "expirado",
  "captura_liberada": false,
  "mensagem": "Licenca expirada. Entre em contato com o suporte VisionAI."
}
```
