# ClAudio — Assistente Autônomo de Automação de Desktop

O ClAudio é um sistema de Inteligência Artificial nativo projetado para operar como um assistente de desktop autônomo. Ele transcende as interações de texto convencionais, integrando comunicação por voz contínua a recursos avançados de automação de sistema operacional no ambiente Windows. Comandado verbalmente, o sistema orquestra softwares, simula interações de interface e otimiza tarefas rotineiras, operando dentro de um Client Kiosk minimalista de processamento local.

---

## Arquitetura e Engenharia de Software

O desenvolvimento deste projeto foi pautado em garantir a integração fluida da IA com a máquina local, mantendo rígidos controles de custos operacionais e alta segurança do ambiente. Os principais pilares técnicos incluem:

### Roteamento Heurístico e Bypass de API (Zero-Cost Local Interception)
A arquitetura implementa uma camada de interceptação semântica pré-LLM. Comandos determinísticos e triviais, como solicitações para abrir o Explorador de Arquivos, Calculadora ou softwares de terceiros, são processados e executados localmente em frações de segundo. Isso reduz o tempo de resposta a zero latência de rede e impede o consumo desnecessário de cotas ou tokens de faturamento das APIs do Google Gemini.

### Sandboxing e Sanitização de Comandos (OS-Level Security)
Para garantir a integridade da máquina anfitriã, métodos baseados na biblioteca Subprocess gerenciam rigorosamente a execução de processos. Scripts independentes, concatenadores de shell e entradas com injeção de parâmetros suspeitos são automaticamente bloqueados ou higienizados. A inteligência operacional restringe a comunicação com o bash nativo do Windows, criando um invólucro de isolamento à prova de prompt injections.

### Interface Kiosk Frameless Baseada em Chromium
A camada visual é alimentada por um processo customizado de Chromium, instanciado isoladamente em um perfil em disco temporário. O backend Python abstrai a biblioteca ctypes do Windows, utilizando funções como EnumWindowsProc para ocultar nativamente bordas, barras de título e controles padrão do SO (minimizar, maximizar). O resultado é uma aplicação limpa de arrasto customizado que interage via servidor assíncrono interno.

### Gestão de Foco Inteligente (Alt+Tab Bypass)
Tendo em vista as barreiras protetivas do kernel do Windows contra alteração abrupta de foco (foreground timeout), desenvolvemos mecanismos espectrais paralelos com a biblioteca PyAutoGUI. Em cenários que exigem preenchimento de formulários ou abertura urgente de aplicativos em segundo plano, o assistente emula pressionamentos artificiais nas raízes da biblioteca User32.dll, ganhando precedência de interface sem violar a fluidez do usuário primário.

### Camada de Persistência com SQLite (Monitoramento de Quota)
Para garantir o rigoroso controle financeiro do usuário e impedir a exaustão de limites tarifários de APIs Cloud (Dev Tiers), o sistema acompanha a contagem diária via banco SQLite no AppData local. Bloqueios cronológicos controlam dinamicamente a cota por IP e limitação por timestamps com resets programados.

---

## Como Executar Localmente

### Requisitos do Sistema
- Sistema Operacional Microsoft Windows.
- Python 3.10 ou superior.
- Navegador Google Chrome ou Microsoft Edge (utilizados como motor de renderização do Client Kiosk).
- Chave de Autenticação da API Google Gemini.

### Instruções de Setup

1. Clone o repositório em seu ambiente local.
2. Inicialize um ambiente virtual (VENV) com o comando:
   `python -m venv venv`
3. Ative seu ambiente virtual correspondente.
4. Realize a instalação de todas as dependências mapeadas:
   `pip install -r requirements.txt`
5. Na raiz do projeto, instancie um arquivo `.env` contendo a variável:
   `GEMINI_API_KEY=sua_chave_aqui`
6. Inicie a execução principal inicializando o módulo:
   `python -m src`

Diga a palavra de ativação: "Cláudio, abra ..."

---
Desenvolvido sob as diretrizes de Clean Architecture, priorizando a estabilidade, segurança modular e a modernidade estética em sistemas nativos de IA.
