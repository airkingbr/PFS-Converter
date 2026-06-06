# PFS Converter

Interface gráfica (GUI) para Windows que automatiza a conversão de arquivos para o formato PlayStation FileSystem (PFS) usando o [MkPFS](https://github.com/PSBrew/MkPFS).

---

## Versões

### v1.0
- Renomeado para **PFS Converter**
- Ícone personalizado no `.exe` e na barra de título
- 4 pipelines de conversão em abas independentes
- Descrição de cada aba explicando o tipo de conversão
- `mkpfs` totalmente embutido no `.exe` (não requer Python ou pip na máquina do usuário)
- OSFMount embutido e instalado silenciosamente na primeira execução
- Correção: arquivo de saída existente é removido antes da conversão (evita prompt interativo `Overwrite?`)
- Correção: erro `parent_pid` ao usar multiprocessing em executável empacotado

### v0.0.2
- Interface dividida em abas independentes
- Nova aba **exfat > ffpfsc**: converte `.exfat` diretamente para `.ffpfsc`
- Nova aba **Dump > exfat**: cria imagem exFAT via OSFMount + robocopy
- Nova aba **Dump > exfat > ffpfsc**: pipeline completo em dois passos
- Pasta separada para arquivos temporários na aba 4 (evita erro de disco cheio)
- Slider de CPU sincronizado entre abas
- Barra de progresso com fase atual e log em tempo real
- Contador de tempo ao final de cada conversão
- Log independente por aba
- Configurações salvas separadamente por aba no `config.json`
- Processo encerrado automaticamente ao fechar a janela
- Janela de console suprimida

### v0.0.1
- Interface gráfica inicial em Python/CustomTkinter
- Aba **Dump > ffpfsc**: converte pasta em `.ffpfsc` em dois passos
- Output preenchido automaticamente com o nome da pasta
- Slider de CPU
- Preferências salvas em `%APPDATA%\PFS Converter\config.json`

---

## Abas

### Dump > ffpfsc
Conversão de Dump (Folder) para Compressed PFS containers (FFPFSC) - Container .dat

Executa dois comandos em sequência:
```
mkpfs pack folder --no-compress --no-adjust-output-file-extension --version PS5 --inode-bits 32 --cpu-count <N> <dump> <pfs_image.dat>
mkpfs pack file --version PS5 --inode-bits 32 --cpu-count <N> --temp-folder <staging> <pfs_image.dat> <saida.ffpfsc>
```

### exfat > ffpfsc
Conversão de exFAT para Compressed PFS containers (FFPFSC)

```
mkpfs pack file --version PS5 --inode-bits 32 --cpu-count <N> --temp-folder <staging> <arquivo.exfat> <saida.ffpfsc>
```

### Dump > exfat
Conversão de Dump (Folder) para exFAT

Usa OSFMount + robocopy via PowerShell para criar uma imagem exFAT montada.

### Dump > exfat > ffpfsc
Conversão de Dump (Folder) para Compressed PFS containers (FFPFSC) - Container exFAT

Pipeline completo: cria imagem exFAT intermediária e converte para `.ffpfsc`.

---

## Configuração salva

As preferências do usuário são armazenadas em:

```
C:\Users\<usuario>\AppData\Roaming\PFS Converter\config.json
```

| Campo | Descrição |
|---|---|
| `temp_file` | Caminho do arquivo temporário `pfs_image.dat` |
| `t1_output_dir` | Último diretório de saída da aba Dump > ffpfsc |
| `t2_output_dir` | Último diretório de saída da aba exfat > ffpfsc |
| `t3_output_dir` | Último diretório de saída da aba Dump > exfat |
| `t4_temp_folder` | Pasta de temporários da aba Dump > exfat > ffpfsc |
| `t4_output_dir` | Último diretório de saída da aba Dump > exfat > ffpfsc |
| `cpu_count` | Número de núcleos selecionados no slider |

---

## Estrutura do projeto

```
GUI-Conversor/
├── gui.py                  # Código principal da interface
├── mkpfs_runner.py         # Wrapper do mkpfs para empacotamento PyInstaller
├── New-OsfExfatImage.ps1   # Script PowerShell para criação de imagens exFAT
├── icon.png                # Ícone fonte (PNG)
├── icon.ico                # Ícone empacotado (multi-resolução)
├── osfmount_setup.exe      # Instalador do OSFMount (embutido no .exe)
└── README.md               # Este arquivo
```
Agradecimentos ao Renan Barreto pelo MKPFS - https://github.com/PSBrew/MkPFS
