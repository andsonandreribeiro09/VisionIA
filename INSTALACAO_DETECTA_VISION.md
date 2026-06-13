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

Para ja ativar a licenca central e limitar a loja a 1 tablet, copie a chave da loja no painel admin e rode:

```powershell
.\preparar_detectavision_cliente.ps1 -LimparBanco -LicenseKey "COLE-A-CHAVE-DA-LOJA"
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

O primeiro tablet que abrir a medicao com a chave da loja fica vinculado como tablet autorizado.
Se precisar trocar o tablet, acesse o admin central e clique em `Liberar troca de tablet`.

## No computador da loja

Abra:

```text
https://detectavision-lab.visioniaotica.com.br
```

## Observacao

Este modo usa banco local SQLite limpo por loja. Ele nao apaga o banco geral de validacao `data\visionai_teste_local.db`.

## Instalador no PC do cliente

No pacote `DetectaVision-Cliente.zip`, abra o PowerShell como administrador dentro da pasta extraida e rode:

```powershell
.\instalar.ps1 -LimparBanco -LicenseKey "COLE-A-CHAVE-DA-LOJA"
```

O instalador cria:

- `C:\VisionAI\DetectaVision`
- icone `VisionAI Laboratorio` na area de trabalho
- icone `Iniciar VisionAI Detecta Vision` na area de trabalho
- inicializacao automatica do sistema ao ligar o Windows
