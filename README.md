# Oiee 🎙️

Ditado por voz local, **100% grátis e offline** — sem
assinatura e sem enviar áudio para lugar nenhum. Segura (ou toca) a tecla, fala,
e o texto transcrito é digitado automaticamente no aplicativo em que você estiver
trabalhando.

---

## 💻 Requisitos

Antes de baixar, confira se a sua máquina atende:

| Item | Mínimo | Recomendado |
|------|--------|-------------|
| Sistema | Windows 10 (64-bit) | Windows 11 |
| Memória RAM | 4 GB | 8 GB ou mais |
| Espaço em disco | ~1 GB (modelo padrão `small`) | ~4 GB (se usar `medium`/`large-v3`) |
| CPU | x86-64 com AVX (Intel/AMD de ~2011 em diante) | — |
| Internet | só na 1ª execução (download do modelo) | — |
| Microfone | qualquer microfone/auricular do Windows | — |

> **Quanto mais rápido o modelo, melhor a experiência**: em máquinas com 4 GB
> de RAM, comece pelo modelo `tiny` ou `base` e suba depois. GPU não é
> obrigatória — a transcrição roda bem em CPU.

---

## 📥 Instalação

**Opção 1 — Instalador (recomendado):** baixe `Oiee-Setup-0.1.1.exe` da
página de [Releases](https://github.com/jessefreire/oiee/releases) e
instale. Cria atalho no menu Iniciar, com desinstalador.

**Opção 2 — Portátil:** baixe e extraia a pasta `Oiee` e execute
`Oiee\Oiee.exe` (não precisa instalar). Manter os arquivos juntos evita a
espera de extração a cada inicialização.

**Opção 3 — Do código:**
```bash
git clone https://github.com/jessefreire/oiee.git
cd oiee
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

> Na primeira execução, o app baixa o modelo de IA escolhido (~75 MB a 3 GB,
> conforme o modelo) e guarda em cache. Depois disso, tudo é local.

---

## 🎮 Como usar

1. Rode o Oiee — aparece uma **barrinha azul flutuante** na tela (por padrão
   centralizada embaixo; arraste-a para onde preferir) e um ícone na bandeja.
2. **Dite**: toque no botão flutuante (ou segure/tocar o atalho), fale, e toque
   de novo para parar — o texto aparece onde o cursor estiver.
3. Configurações: **clique com o botão direito** no botão flutuante, ou
   **botão direito no ícone da bandeja** → **Configurações**.

### Botão flutuante 🎤

- **Ocioso**: **barrinha horizontal azul bem pequena** (estilo Flow Bar do
  Wispr Flow), sempre visível, **arrastável** (a posição é lembrada entre
  sessões). Por padrão ela nasce **centralizada embaixo, um pouco acima da
  barra de tarefas** — e clareia quando o mouse passa por cima;
- **Gravando**: vira um cartão com as **ondas sonoras ao vivo** e o tempo de
  gravação — fale olhando pra ele, igual ao Oiee.
- **Clique** para ligar/desligar a gravação, em qualquer momento.

### Atalhos disponíveis

(Alternativa ao botão flutuante — pode usar os dois ao mesmo tempo.)

| Atalho | Modo |
|---|---|
| **Ctrl + Win** (padrão) | **segurar** = fala enquanto a tecla estiver pressionada |
| **Ctrl + Win** (padrão) | **toque duplo** = liga/desliga a gravação (toggle) |

> O atalho funciona com um único toque duplo (não precisa de hook de teclado
> antes de iniciar), nunca "reinicia" sozinho se você parar gravando com um
> toque rápido, e **ignora combos do Windows** — `Ctrl+Win` junto com setas,
> `D` ou outra tecla (desktops virtuais, etc.) nunca dispara gravação.

---

## Escolhendo o modelo

| Modelo | Tamanho | Qualidade | Velocidade (CPU) |
|--------|---------|-----------|------------------|
| `tiny` | 75 MB | baixa | instantâneo |
| `base` | 145 MB | boa | rápido |
| `small` | 460 MB | muito boa | moderado ⭐ padrão |
| `medium` | 1,5 GB | excelente | lento |
| `large-v3` | 3 GB | melhor | bem lento |

---

## 🧠 Perfil linguístico local

O Oiee pode reduzir erros recorrentes sem enviar gravações para a internet e
sem retreinar o modelo de IA. Em **Configurações** você encontra:

- **Meu vocabulário**: termos técnicos, nomes, siglas e marcas (ex.:
  `Kubernetes`, `Power BI`, `pull request`) com prioridade na transcrição —
  o principal remédio para termos em inglês saírem errados;
- **Revisar antes de inserir**: exibe o texto antes de colar. Ao corrigir e
  escolher **Inserir e aprender**, o Oiee memoriza apenas as trocas
  confirmadas (por exemplo, `jece` → `Jesse`);
- **Gerenciar correções aprendidas**: permite editar ou apagar cada correção,
  ou limpar tudo quando quiser;
- **Limpar texto automaticamente**: remove muletas de fala (*"ahm", "tipo"*)
  e repetições, e capitaliza as frases — pode ser desligada;
- **Iniciar com o Windows**: registro no registro do Windows (HKCU `Run`),
  com caixa de seleção nas Configurações e tarefa opcional no instalador.

O perfil fica no `config.json` do próprio computador. Áudio não é salvo e
nada é enviado à nuvem. A revisão vem desativada por padrão para manter o
ditado instantâneo.

---

## 🌐 Idiomas

São **99 idiomas** do Whisper + detecção automática, todos com rótulo em
português na Configurações → Idioma. Por padrão, o app transcreve em
**português brasileiro**.

Os **comandos por voz** seguem o idioma escolhido: há tabela própria para
`pt`, `en`, `es` e `fr` (nos demais idiomas vale a tabela em português).

---

## 📌 Snippets

Snippet é um **texto pronto** disparado por uma palavra falada — perfeito para
respostas repetitivas, assinaturas e endereços:

1. Em Configurações → **Gerenciar snippets**, cadastre no formato
   `atalho => texto` (ex.: `agenda => Reunião de 30 min? https://calendly.com/...`);
   use `\n` para quebra de linha;
2. Durante o ditado, diga **`snippet` + o atalho** (ex.: *"snippet agenda"*);
3. O texto pronto entra no lugar — sem diferenciar maiúsculas/acentos, e o
   nome mais longo tem prioridade.

A expansão acontece depois da limpeza e dos comandos por voz: o corpo do
snippet entra como texto final. Tudo fica no `config.json` local.

---

## Comandos por voz 🗣️

Diga um destes comandos durante o ditado — a tabela segue o idioma escolhido
(`pt`, `en`, `es`, `fr`; nos demais vale a de português):

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

## 🔒 Privacidade e dados

Em Configurações → **Privacidade e dados** você vê a declaração completa do
app. Resumindo:

- A transcrição roda **100% local** — sem servidores, sem conta, sem limite
  de palavras, sem telemetria;
- O **único** acesso à internet é o download do modelo na primeira
  execução (Hugging Face); depois, tudo offline;
- Vocabulário, correções e snippets ficam só no `config.json` deste PC;
- Único arquivo de log: `oiee-error.log` (erros técnicos, local).

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

## 💛 Apoie o projeto

O Oiee é gratuito e sem anúncios. Se está te ajudando, você pode apoiar o
desenvolvimento contínuo via
**[GitHub Sponsors](https://github.com/sponsors/jessefreire)** — o valor é
reinvestido em tempo de desenvolvimento, assinaturas de infraestrutura e
novos recursos.

---

## 🔧 Para desenvolvedores

```bash
# ambiente de build isolado e estável (criado uma única vez)
py -3.11 -m venv .venv-build
.venv-build\Scripts\pip install -r requirements-build.txt

# gera a pasta portátil de inicialização rápida (dist/Oiee/Oiee.exe)
powershell -ExecutionPolicy Bypass -File build_exe.ps1

# gera o instalador (dist/Oiee-Setup-<versão>.exe) — requer Inno Setup 6
#   winget install JRSoftware.InnoSetup
"C:\Users\<você>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss

# testes
powershell -ExecutionPolicy Bypass -File scripts/make_test_audio.ps1   # gera áudio de exemplo
.venv\Scripts\python tests\test_pipeline.py
```

---

## Problemas comuns

- **A primeira fala demora**: o modelo é pré-carregado em background ao abrir
  o app — passe o mouse no ícone da bandeja: "carregando modelo…" vira o
  atalho quando estiver pronto. Na primeiríssima execução ele é baixado
  (~75 MB a 3 GB, conforme o modelo). Depois disso, tudo é local e rápido.
- **Não digita em apps como administrador**: o hook global do Windows não enxerga
  teclas em janelas elevadas. Rode o Oiee como administrador nesse caso.
- **Texto sai sem acentos ou o app "engole" caracteres**: troque para o modo
  **Colar** nas configurações.
- **Nada é transcrito**: confira o microfone nas configurações e o volume de
  entrada do Windows.
- **O app fechou sozinho**: procure o arquivo `oiee-error.log` ao lado do
  executável e cole o conteúdo na sua issue do GitHub.

---

## 📄 Licença

Distribuído sob **GNU GPLv3** (ver [LICENSE](LICENSE)) — pode usar, modificar
e redistribuir livremente, desde que as derivativas mantenham o código aberto
e a mesma licença.

---

## Estrutura

```
main.py              # ponto de entrada (mutex single-instance + boot)
flow/
  config.py          # configuração em config.json (modelo, idioma, snippets…)
  recorder.py        # gravação do microfone (sounddevice)
  transcriber.py     # transcrição local (faster-whisper, CPU int8)
  commands.py        # comandos por voz (pt/en/es/fr: pontuação, linhas, edição)
  snippets.py        # expansão de snippets ("snippet <atalho>" -> texto pronto)
  cleanup.py         # limpeza de texto (fillers, repetições, capitalização)
  autostart.py       # iniciar com o Windows (HKCU Run, só no .exe)
  typer.py           # digita/cola o texto e executa ações de teclado
  engine.py          # gravar -> transcrever -> limpar -> comandos -> digitar
  qt_app.py          # UI Qt: overlay, bandeja, configurações, diálogos
assets/              # ícones do app
scripts/             # utilitários (ícone, áudio de teste, build)
tests/               # testes ponta a ponta (53)
build_exe.ps1        # build do .exe com PyInstaller
installer.iss        # script do instalador (Inno Setup)
```
