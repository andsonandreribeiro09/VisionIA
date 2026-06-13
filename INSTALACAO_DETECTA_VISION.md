# Instalacao Detecta Vision Osasco

Este roteiro instala a loja Detecta Vision Osasco usando banco local limpo.

## Enderecos da loja

Tablet de medicao:

```text
https://detectavision-medicao.visioniaotica.com.br
```

Computador/laboratorio:

```text
https://detectavision-lab.visioniaotica.com.br
```

## Banco da loja

O banco local da loja fica separado da base de validacao:

```text
data\clientes\detecta-vision-osasco-001\visionai.db
data\clientes\detecta-vision-osasco-001\pacientes_medicoes.csv
```

## Preparar banco limpo

No PowerShell, dentro da pasta do sistema:

```powershell
.\preparar_detectavision_cliente.ps1 -LimparBanco
```

Esse comando cria um perfil local:

```text
.env.detectavision.local
```

Se ja existir banco anterior dessa loja, ele e arquivado em:

```text
data\backups
```

## Iniciar medicao

Abra uma janela do PowerShell:

```powershell
.\iniciar_detectavision_medicao.ps1
```

## Iniciar laboratorio

Abra outra janela do PowerShell:

```powershell
.\iniciar_detectavision_laboratorio.ps1
```

## Iniciar tunel fixo

Abra outra janela do PowerShell:

```powershell
.\iniciar_tunel_local.ps1
```

## No tablet

Abra:

```text
https://detectavision-medicao.visioniaotica.com.br
```

Depois adicione na tela inicial do iPad/tablet.

## No computador da loja

Abra:

```text
https://detectavision-lab.visioniaotica.com.br
```

## Observacao

Este modo usa banco local SQLite limpo por loja. Ele nao apaga o banco geral de validacao `data\visionai_teste_local.db`.
