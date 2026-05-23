# VisionAI local

## 1. Configurar o banco de teste

Para validacao no tablet, o script usa SQLite local por padrao. Isso evita a latencia de gravar cadastro e medicoes no PostgreSQL do Render durante cada atendimento.

O arquivo fica em:

```text
data\visionai_teste_local.db
data\pacientes_medicoes.csv
```

Se quiser testar gravando direto no PostgreSQL Render, crie ou edite o `.env.local` com:

```text
VISIONAI_USE_RENDER_DB=1
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

## 4. Abrir o laboratorio local

Abra outro PowerShell na pasta do projeto e rode:

```powershell
.\iniciar_laboratorio_local.ps1
```

No computador da loja, abra:

```text
http://localhost:5001/laboratorio
```

Esse painel local lê o mesmo banco SQLite de teste usado pela medição local.

## Parametros do modo local

O script local usa:

- score minimo: 82
- tempo parado: 900 ms
- capturas por medicao: 3
- lote aprovado apenas quando as leituras ficam com baixa variacao
- calibracao facial so e aplicada quando tiver pelo menos 3 amostras confiaveis
- DP muito fora da faixa segura pede nova medicao em vez de salvar
- banco padrao: SQLite local de teste
- CSV local: `data\pacientes_medicoes.csv`
- resultado final: mediana das 3 capturas, para reduzir queda causada por uma captura isolada
- foto enviada: reduzida para acelerar o salvamento pelo tunel
- fator local de escala: 1.04, para compensar a tendencia do tablet medir DP um pouco abaixo

Para alterar, defina estas variaveis no `.env.local`:

```text
VISIONAI_UI_CAPTURE_SCORE_MIN=82
VISIONAI_UI_CAPTURE_HOLD_MS=900
VISIONAI_UI_TOTAL_CAPTURES=3
VISIONAI_UI_PHOTO_MAX_WIDTH=720
VISIONAI_UI_PHOTO_QUALITY=0.68
VISIONAI_USE_MEDIAN_RESULT=1
VISIONAI_SCALE_MULTIPLIER=1.04
```
