# VisionAI local

## 1. Configurar o banco Render

Crie um arquivo chamado `.env.local` na pasta do projeto.

Use este modelo:

```text
DATABASE_URL=postgresql://usuario:senha@host/database
VISIONAI_LAB_URL=https://visionai-laboratorio.onrender.com/laboratorio
```

Use a URL completa do PostgreSQL do Render em `DATABASE_URL`.

## 2. Iniciar a medicao local

Abra um PowerShell na pasta do projeto e rode:

```powershell
.\iniciar_medicao_local.ps1
```

Deixe essa janela aberta.

## 3. Abrir o tunel HTTPS

Abra outro PowerShell na pasta do projeto e rode:

```powershell
.\iniciar_tunel_local.ps1
```

Abra no tablet a URL `https://...trycloudflare.com` que aparecer.

## Parametros do modo local

O script local usa:

- score minimo: 82
- tempo parado: 1800 ms
- capturas por medicao: 6
- lote aprovado apenas quando as leituras ficam com baixa variacao
- banco obrigatorio: PostgreSQL Render

Para alterar, defina estas variaveis no `.env.local`:

```text
VISIONAI_UI_CAPTURE_SCORE_MIN=82
VISIONAI_UI_CAPTURE_HOLD_MS=1800
VISIONAI_UI_TOTAL_CAPTURES=6
```
