# PFS Converter

Interface gráfica (GUI) para Windows que automatiza a conversão de dumps PS5 para os formatos PlayStation FileSystem (PFS) usando o [MkPFS](https://github.com/PSBrew/MkPFS).

> **Requer privilégios de administrador** — necessário para operações de montagem via OSFMount.

---

## Interface

O layout é dividido em 4 painéis:

| Painel | Posição | Conteúdo |
|--------|---------|----------|
| **1 — Source** | Topo esquerdo | Seletor de dump (pasta ou `.exfat`), info do jogo (capa, TitleID, versão, tamanho) |
| **2 — Format & Output** | Topo direito | Cards de formato, preset de nome, barra de progresso |
| **3 — Configure Output** | Baixo esquerdo | Pasta de saída, pasta temporária |
| **4 — Advanced Options** | Baixo direito | CPU threads, compression engine, compression level |

Barra de navegação superior: **Converter** | **Extrair** | **▶ Build**

---

## Formatos suportados

### Converter (view principal)

| Formato | Descrição | Saída |
|---------|-----------|-------|
| **exFAT** | Cria imagem exFAT montável via OSFMount | `.exfat` |
| **PFS Raw** | Dump → `pfs_image.dat` → PFS comprimido | `.ffpfsc` |
| **PFS exFAT** | Dump → `.exfat` → PFS comprimido | `.ffpfsc` |

### Fonte de entrada

- **Pasta do dump** — seleciona a pasta raiz do dump PS5; lê `sce_sys/param.json` (ou `param.sfo`) e `sce_sys/icon0.png` para exibir info do jogo
- **Arquivo .exfat** — seleciona uma imagem `.exfat` já existente; monta via OSFMount para ler os metadados e converte direto para `.ffpfsc`

### Extrair (view separada)

Extrai arquivos de imagens PFS (`.ffpfsc`, `.ffpfs`, `.exfat`) usando `mkpfs unpack`.

Opções: `--deep` (extrai arquivos internos) e `--overwrite` (sobrescreve existentes).

---

## Opções avançadas

| Opção | Padrão | Descrição |
|-------|--------|-----------|
| CPU threads | Auto | Número de threads paralelos durante a conversão |
| Compression engine | zlib | `zlib` (estável) ou `zlib-isa` (experimental) |
| Compression level | 9 | 1 (mínima) a 9 (máxima) |

---

## Preset de nome do arquivo de saída

| Preset | Exemplo |
|--------|---------|
| Title ID | `PPSA12345.ffpfsc` |
| + Título | `PPSA12345 - Nome do Jogo.ffpfsc` |
| + Versão | `PPSA12345 - Nome do Jogo (01.00).ffpfsc` |
| Personalizado | livre |

---

## Log de conversão

O log fica oculto por padrão. Clique em **📋 Log** (ao lado da barra de progresso) para abrir uma janela flutuante que espelha a saída em tempo real.

---

## Comandos executados

### PFS Raw
```
mkpfs pack folder --raw --no-compress --no-adjust-output-file-extension \
  --version PS5 --inode-bits 32 --cpu-count <N> <dump> pfs_image.dat

mkpfs pack file --version PS5 --inode-bits 32 --cpu-count <N> \
  --temp-folder <staging> [--compression-backend zlib-isa] \
  --compression-level <N> pfs_image.dat <saida.ffpfsc>
```

### PFS exFAT
```
# Passo 1: criar imagem exFAT via PowerShell + OSFMount
New-OsfExfatImage.ps1 -ImagePath <temp.exfat> -SourceDir <dump> -ForceOverwrite

# Passo 2: comprimir para ffpfsc
mkpfs pack file --version PS5 --inode-bits 32 --cpu-count <N> \
  --temp-folder <staging> --compression-level <N> <temp.exfat> <saida.ffpfsc>
```

### exFAT
```
New-OsfExfatImage.ps1 -ImagePath <saida.exfat> -SourceDir <dump> -ForceOverwrite
```

### Arquivo .exfat → ffpfsc (modo fonte direto)
```
mkpfs pack file --version PS5 --inode-bits 32 --cpu-count <N> \
  --temp-folder <staging> --compression-level <N> <arquivo.exfat> <saida.ffpfsc>
```

### Extrair
```
mkpfs unpack --no-progress [--overwrite] [--deep] <imagem> <pasta_destino>
```

---

## Configuração salva

As preferências são armazenadas em:

```
C:\Users\<usuario>\AppData\Roaming\PFS Converter\config.json
```

| Campo | Descrição |
|-------|-----------|
| `fmt` | Formato selecionado (`exfat`, `pfs_raw`, `pfs_exfat`) |
| `comp_engine` | Engine de compressão (`zlib`, `zlib-isa`) |
| `comp_level` | Nível de compressão (1–9) |
| `name_preset` | Preset de nome (`id`, `id_title`, `id_title_ver`, `custom`) |
| `cpu_count` | Número de CPUs selecionado no slider |
| `out_folder` | Última pasta de saída |
| `temp_folder` | Última pasta temporária |
| `t5_output_dir` | Último diretório de saída da aba Extrair |

---

## Estrutura do projeto

```
GUI-Conversor/
├── gui.py                  # Código principal da interface
├── mkpfs_runner.py         # Wrapper do mkpfs para empacotamento PyInstaller
├── app.manifest            # Manifesto UAC (requireAdministrator)
├── New-OsfExfatImage.ps1   # Script PowerShell para criação de imagens exFAT
├── icon.png                # Ícone fonte (PNG)
├── icon.ico                # Ícone empacotado (multi-resolução)
├── osfmount_setup.exe      # Instalador do OSFMount (embutido no .exe)
└── README.md               # Este arquivo
```

---

## Build

### Pré-requisitos

```bash
pip install customtkinter pillow pyinstaller
pip install mkpfs
```

### Compilar mkpfs_cli.exe

```bash
python -m PyInstaller --onefile --name mkpfs_cli mkpfs_runner.py
```

> **Sem** `--noconsole` — necessário para que erros vão para stdout (não para dialog bloqueante).

### Compilar PFS Converter.exe

```bash
python -m PyInstaller --noconfirm --onefile --noconsole --uac-admin \
  --name "PFS Converter" --icon icon.ico \
  --add-data "icon.ico;." \
  --add-data "New-OsfExfatImage.ps1;." \
  --add-data "osfmount_setup.exe;." \
  --add-data "mkpfs_cli.exe;." \
  gui.py
```

`--uac-admin` — solicita elevação UAC automaticamente (necessário para OSFMount).

---

## Histórico de versões

### v1.2.1
- Log abre ao lado da janela principal (sem sobreposição), com a mesma altura

### v1.2.0
- **Redesign completo da interface** — layout 4 painéis (2×2)
- Source mode: pasta de dump **ou** arquivo `.exfat` existente
- Modo `.exfat`: monta via OSFMount, lê metadados do jogo e converte direto para `.ffpfsc`
- Advanced Options sempre visível no painel 4 (sem toggle colapsável)
- Botão **▶ Build** fixo na barra de navegação superior
- Log em janela popup separada com espelhamento em tempo real
- Janela redimensionável (mínimo 960×680)
- Cards de formato clicáveis em toda a área
- Nível de compressão padrão alterado para **9 — Máxima**
- Preset de nome: formato `TitleID - Titulo (versao).ffpfsc`
- Fix: arquivo intermediário PFS Raw sempre nomeado `pfs_image.dat`
- Elevação UAC automática via `--uac-admin`

### v1.1.2
- Painel de info do jogo: capa, título, TitleID, versão, tamanho do dump
- Suporte a `param.json` (PS5) além de `param.sfo` (PS4/legado)
- Fix: `contentVersion` usado como versão (não `masterVersion`)

### v1.1.1
- Fix: detecção de sucesso por existência do arquivo de saída quando mkpfs retorna erro por emoji 🎉 (UnicodeEncodeError no stdout cp1252)
- `mkpfs_cli.exe` compilado sem `--noconsole` para que erros vão ao pipe stdout

### v1.0.9
- Aba **Extrair** (mkpfs unpack) com opções `--deep` e `--overwrite`

### v1.0.8
- Fix: pasta de saída padrão é o pai da pasta selecionada (não dentro dela)

### v1.0.6 – v1.0.7
- Atualização mkpfs 0.0.8 → 0.0.9
- Fix: adicionado `--raw` ao comando `pack folder` para compatibilidade com mkpfs 0.0.9
- Fix: `PYTHONIOENCODING=utf-8` nos subprocessos para tratar emoji no output

### v1.0.0 – v1.0.5
- Interface com 4 abas independentes de conversão
- Ícone personalizado no `.exe`
- `mkpfs` totalmente embutido no `.exe`
- OSFMount embutido e instalado silenciosamente na primeira execução
- Fix: arquivo de saída existente removido antes da conversão
- Fix: erro `parent_pid` ao usar multiprocessing em executável empacotado

### v0.0.2
- Interface dividida em abas independentes
- Nova aba **exfat > ffpfsc**: converte `.exfat` diretamente para `.ffpfsc`
- Nova aba **Dump > exfat**: cria imagem exFAT via OSFMount + PowerShell
- Nova aba **Dump > exfat > ffpfsc**: pipeline completo em dois passos
- Barra de progresso com fase atual e log em tempo real
- Slider de CPU sincronizado entre abas

### v0.0.1
- Versão inicial
- Interface gráfica básica em Python/CustomTkinter
- Aba **Dump > ffpfsc**: converte pasta em `.ffpfsc` em dois passos
- Preferências salvas em `%APPDATA%\PFS Converter\config.json`

---

Agradecimentos ao Renan Barreto pelo MkPFS — https://github.com/PSBrew/MkPFS
