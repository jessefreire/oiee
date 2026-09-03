# Oiee 🎙️

Ditado por voz local, **100% grátis e offline** — sem
assinatura e sem enviar áudio para lugar nenhum. Segura (ou toca) a tecla, fala,
e o texto transcrito é digitado automaticamente no aplicativo em que você estiver
trabalhando.

---

## 📥 Instalação

**Opção 1 — Instalador (recomendado):** baixe `Oiee-Setup-0.1.0.exe` da
página de [Releases](https://github.com/SEU_USUARIO/flow-local/releases) e
instale. Cria atalho no menu Iniciar, com desinstalador.

**Opção 2 — Portátil:** baixe `Oiee.exe` e rode direto (não precisa
instalar).

**Opção 3 — Do código:**
```bash
git clone https://github.com/SEU_USUARIO/oiee.git
cd oiee
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

> Na primeira execução, o app baixa o modelo de IA escolhido (~75 MB a 3 GB,
> conforme o modelo) e guarda em cache. Depois disso, tudo é local.

---

## 🎮 Como usar

1. Rode o Oiee — aparece um **botão flutuante de microfone** na tela
   (arraste-o para onde preferir) e um ícone na bandeja.
2. **Dite**: toque no botão flutuante (ou segure/tocar o atalho), fale, e toque
   de novo para parar — o texto aparece onde o cursor estiver.
3. Configurações: **clique com o botão esquerdo** no ícone da bandeja (ou direito
   → menu) → **Configurações**.

### Botão flutuante 🎤

- **Ocioso**: bolinha azul de microfone, sempre visível, **arrastável** (a
  posição é lembrada entre sessões).
- **Gravando**: vira um cartão com as **ondas sonoras ao vivo** e o tempo de
  gravação — fale olhando pra ele, igual ao Wispr.
- **Clique** para ligar/desligar a gravação, em qualquer momento.
- Pode ser ocultado em Configurações → Interface.

### Atalhos disponíveis

(Alternativa ao botão flutuante — pode usar os dois ao mesmo tempo.)

| Atalho | Modo |
|---|---|
| Alt Direito (padrão) | segurar |
| Caps Lock | segurar |
| F9 | segurar |
| Ctrl + Win | alternar |
| Ctrl + Espaço | alternar |
| Personalizado (ex.: `ctrl+alt+f7`) | segurar ou alternar |

> ⚠️ **Ctrl + Espaço** é o atalho padrão do Windows para alternar idioma de
> entrada (IME) em algumas configurações — se isso te atrapalhar, use outro.

---

## Escolhendo o modelo

| Modelo | Tamanho | Qualidade | Velocidade (CPU) |
|--------|---------|-----------|------------------|
| `tiny` | 75 MB | baixa | instantâneo |
| `base` | 145 MB | boa | rápido ⭐ padrão |
| `small` | 460 MB | muito boa | moderado |
| `medium` | 1,5 GB | excelente | lento |
| `large-v3` | 3 GB | melhor | bem lento |

---

## 🧠 Perfil linguístico local

O Oiee pode reduzir erros recorrentes sem enviar gravações para a internet e
sem retreinar o modelo de IA. Em **Configurações** você encontra:

- **Meu vocabulário**: nomes, clientes, siglas, marcas e projetos que devem
  receber prioridade na transcrição;
- **Revisar antes de inserir**: exibe o texto antes de colar. Ao corrigir e
  escolher **Inserir e aprender**, o Oiee memoriza apenas as trocas
  confirmadas (por exemplo, `jece` → `Jesse`);
- **Gerenciar correções aprendidas**: permite editar ou apagar cada correção,
  ou limpar tudo quando quiser.

O perfil fica no `config.json` do próprio computador. Áudio não é salvo e
nada é enviado à nuvem. A revisão vem desativada por padrão para manter o
ditado instantâneo.

---

## Comandos por voz 🗣️

Diga um destes comandos durante o ditado (português por padrão; em `en` vale a
tabela em inglês):

| Você diz | Acontece |
|---|---|
| `vírgula` | `,` |
| `ponto final` | `.` |
| `ponto de interrogação` / `interrogação` | `?` |
| `ponto de exclamação` / `exclamação` | `!` |
| `dois pontos` / `ponto e vírgula` / `reticências` | `:` `;` `…` |
| `barra` / `arroba` | `/` `@` |
| `abre aspas` / `fecha aspas` | `"` |
| `nova linha` / `quebrar linha` | Enter |
| `novo parágrafo` | Enter Enter |
| `apagar última palavra` | Ctrl+Backspace |
| `cursor para cima/baixo/esquerda/direita` | setas |
| `início da linha` / `fim da linha` | Home / End |

Exemplo: "hoje **vírgula** vamos sair **ponto final**" → `hoje, vamos sair.`

---

## 💚 Apoie o projeto

O Oiee é **gratuito e open source** (licença MIT). Se ele te ajudar no dia
a dia e você quiser contribuir, qualquer valor é bem-vindo:

**Pix:** *(adicione sua chave em Configurações → "Apoie o projeto" — ela fica
salva em `config.json` e pode ser copiada com um clique)*

---

## 🤝 Contribuição

Todo mundo é bem-vindo — é só escolher o que combina com você:

- **Encontrou um bug?** Abra uma issue usando o template de *bug report*
  (cole o conteúdo de `oiee-error.log`, se houver).
- **Tem uma ideia?** Abra uma issue de *feature request* contando o problema que
  você quer resolver.
- **Quer codar?** Veja as issues abertas, ou proponha sua própria mudança:
  1. Faça um fork e crie uma branch (`git checkout -b minha-melhoria`).
  2. Implemente com calma, seguindo o estilo do projeto (comentários em
     português, código simples e direto).
  3. Rode os testes: `.venv\Scripts\python tests\test_pipeline.py` — tudo verde
     antes de abrir o PR.
  4. Abra um Pull Request descrevendo **o que** mudou e **porquê**.

Boas primeiras issues: melhorar as tabelas de comandos de voz, traduções,
ajustes de UI, performance da transcrição, documentação.

---

## 🔧 Para desenvolvedores

```bash
# ambiente de build isolado e estável (criado uma única vez)
py -3.11 -m venv .venv-build
.venv-build\Scripts\pip install -r requirements-build.txt

# gera o .exe portátil (dist/Oiee.exe)
powershell -ExecutionPolicy Bypass -File build_exe.ps1

# gera o instalador (dist/Oiee-Setup-<versão>.exe) — requer Inno Setup 6
#   winget install JRSoftware.InnoSetup
"C:\Users\<você>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss

# testes
powershell -ExecutionPolicy Bypass -File scripts/make_test_audio.ps1   # gera áudio de exemplo
.venv\Scripts\python tests\test_pipeline.py
```

Antes de publicar no GitHub: troque `SEU_USUARIO` pela sua conta no
`installer.iss` (AppPublisherURL) e no README, e atualize a versão.

---

## Problemas comuns

- **A primeira fala demora**: o modelo está sendo baixado/carregado. O app já
  pré-carrega em background ao iniciar.
- **Não digita em apps como administrador**: o hook global do Windows não enxerga
  teclas em janelas elevadas. Rode o Oiee como administrador nesse caso.
- **Texto sai sem acentos ou o app "engole" caracteres**: troque para o modo
  **Colar** nas configurações.
- **Nada é transcrito**: confira o microfone nas configurações e o volume de
  entrada do Windows.
- **O app fechou sozinho**: procure o arquivo `oiee-error.log` ao lado do
  executável e cole o conteúdo na sua issue do GitHub.

---

## Estrutura

```
main.py              # ponto de entrada (bandeja + hotkey)
flow/
  config.py          # configuração persistida em config.json (atalho, Pix, modelo…)
  recorder.py        # gravação do microfone (sounddevice)
  transcriber.py     # transcrição local (faster-whisper, CPU int8)
  commands.py        # comandos por voz (pontuação, linhas, edição)
  typer.py           # digita/cola o texto e executa ações de teclado
  engine.py          # hotkey (segurar/alternar) -> gravar -> transcrever -> digitar
  overlay.py         # UI em CustomTkinter: overlay "gravando…" + configurações
  tray.py            # ícone na bandeja (pystray)
assets/              # ícones do app
scripts/             # utilitários (ícone, áudio de teste, build)
tests/               # testes ponta a ponta
build_exe.ps1        # build do .exe com PyInstaller
installer.iss        # script do instalador (Inno Setup)
```
