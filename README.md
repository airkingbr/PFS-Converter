# PFS Converter

Interface gráfica (GUI) para Windows que automatiza a conversão de arquivos para o formato PlayStation FileSystem (PFS) usando o [MkPFS](https://github.com/PSBrew/MkPFS).

---

## Versões

### v0.0.2
- Interface dividida em duas abas independentes
- Nova aba **exfat > ffpfsc**: converte um arquivo `.exfat` diretamente para `.ffpfsc` com um único comando
- Output preenchido automaticamente com o nome do arquivo de origem ao selecionar o `.exfat`
- Slider de CPU sincronizado entre as duas abas
- Log independente por aba
- Configurações salvas separadamente por aba no `config.json`
- Processo `mkpfs` encerrado automaticamente ao fechar a janela
- Janela de console suprimida (sem tela preta ao abrir o `.exe`)
- Arquivo temporário `pfs_image.dat` removido automaticamente ao final de cada conversão

### v0.0.1
- Interface gráfica inicial em Python/CustomTkinter
- Aba **Pasta > ffpfsc**: converte pasta de arquivos em imagem `.ffpfsc` em dois passos
  - Passo 1: `mkpfs pack folder` gera `pfs_image.dat` intermediário
  - Passo 2: `mkpfs pack file` converte o intermediário para `.ffpfsc` final
- Seleção visual de pasta de entrada, arquivo temporário e arquivo de saída
- Output preenchido automaticamente com o nome da pasta ao selecionar a entrada
- Slider para escolher quantidade de núcleos de CPU (detecta o total da máquina)
- Log em tempo real do progresso da conversão
- Preferências salvas em `%APPDATA%\PFS Converter\config.json`
- `--temp-folder` apontado para o mesmo drive do `pfs_image.dat` para evitar erro de hard link entre drives

---

## Abas

### Pasta > ffpfsc

Converte uma pasta inteira em imagem PFS. Executa dois comandos em sequência:

**Passo 1 — Pack Folder**
```
mkpfs pack folder --no-compress --no-adjust-output-file-extension --version PS5 --inode-bits 32 --cpu-count <N> <pasta_entrada> <pfs_image.dat>
```

**Passo 2 — Pack File**
```
mkpfs pack file --version PS5 --inode-bits 32 --cpu-count <N> --temp-folder <dir_temp> <pfs_image.dat> <saida.ffpfsc>
```

### exfat > ffpfsc

Converte um arquivo `.exfat` diretamente para `.ffpfsc`. Executa um único comando:

```
mkpfs pack file --version PS5 --inode-bits 32 --cpu-count <N> --temp-folder <dir_origem> <arquivo.exfat> <saida.ffpfsc>
```

---

## Configuração salva

As preferências do usuário são armazenadas em:

```
C:\Users\<usuario>\AppData\Roaming\PFS Converter\config.json
```

Campos salvos:
| Campo | Descrição |
|---|---|
| `temp_file` | Caminho do arquivo temporário `pfs_image.dat` |
| `t1_output_dir` | Último diretório de saída da aba Pasta > ffpfsc |
| `t2_output_dir` | Último diretório de saída da aba exfat > ffpfsc |
| `cpu_count` | Número de núcleos selecionados no slider |

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
pyinstaller --onefile --windowed --noconsole --name "PFS Converter" gui.py
```

O executável será gerado em `dist\PFS Converter.exe`.

---

## Estrutura do projeto

```
GUI-Conversor/
├── gui.py       # Código principal da interface
└── README.md    # Este arquivo
```
