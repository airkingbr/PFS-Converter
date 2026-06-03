# MkPFS Converter

Interface gráfica (GUI) para Windows que automatiza a conversão de pastas em imagens PlayStation FileSystem (PFS) usando o [MkPFS](https://github.com/PSBrew/MkPFS).

---

## O que ele faz

Executa dois comandos do `mkpfs` em sequência a partir de uma interface visual simples:

**Passo 1 — Pack Folder**
```
mkpfs pack folder --verify --no-compress --no-adjust-output-file-extension --version PS5 --inode-bits 32 --cpu-count <N> <pasta_entrada> <pfs_image.dat>
```

**Passo 2 — Pack File**
```
mkpfs pack file --verify --version PS5 --inode-bits 32 --cpu-count <N> --temp-folder <dir_temp> <pfs_image.dat> <saida.ffpfsc>
```

---

## Funcionalidades

- Seleção visual de pasta de entrada, arquivo temporário e arquivo de saída
- Slider para escolher quantos núcleos de CPU utilizar (detecta o total da máquina automaticamente)
- Log em tempo real do progresso da conversão
- Salva automaticamente os caminhos de temp e output para próximas utilizações (`%APPDATA%\MkPFS Converter\config.json`)
- Remove o arquivo temporário anterior automaticamente antes de cada conversão
- O `--temp-folder` do passo 2 é sempre definido no mesmo drive do `pfs_image.dat` para evitar erro de hard link entre drives

---

## Requisitos

- Python 3.8+
- `mkpfs` instalado (`pip install mkpfs`)
- `customtkinter` instalado (`pip install customtkinter`)

---

## Como rodar

```
python gui.py
```

---

## Como gerar o .exe

```
pip install pyinstaller
pyinstaller --onefile --windowed --name "MkPFS Converter" gui.py
```

O executável será gerado em `dist\MkPFS Converter.exe`.

---

## Configuração salva

As preferências do usuário são armazenadas em:

```
C:\Users\<usuario>\AppData\Roaming\MkPFS Converter\config.json
```

Campos salvos:
- `temp_file` — caminho do arquivo temporário `pfs_image.dat`
- `output_dir` — último diretório de saída utilizado
- `cpu_count` — número de núcleos selecionados no slider

---

## Estrutura do projeto

```
GUI-Conversor/
├── gui.py       # Código principal da interface
└── README.md    # Este arquivo
```
