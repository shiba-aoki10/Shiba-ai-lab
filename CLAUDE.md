# SHIBA AI LAB — Memória do projeto

Leia este arquivo inteiro antes de qualquer ação. Ele existe para que o Shiba
não precise repetir contexto entre conversas. Responda sempre em português do Brasil.

## Regras de trabalho
- **Não instalar, não apagar e não modificar projetos existentes sem autorização explícita.**
- Nada de comandos destrutivos. Antes de sobrescrever algo, olhar o que existe.
- Não enviar dados pessoais (caminhos, arquivos, nome do PC) para serviços externos.
- Minimizar idas e vindas: executar o que já foi autorizado sem pedir de novo a cada passo;
  pedir aprovação só para instalar, apagar, publicar ou gastar dinheiro.
- Ao terminar algo, atualizar a seção **Status** abaixo e fazer commit.

## Onde a sessão está rodando (verificar primeiro)
- Sessão **na nuvem** (ambiente "Default", Linux, sem GPU): só serve para escrever
  scripts, docs e estrutura no GitHub. Não enxerga o PC.
- Sessão **local** ("This computer", no app desktop do Claude no Windows): acessa
  GPU, programas e arquivos. Toda execução de auditoria, instalação e áudio é aqui.
- Teste rápido: `$env:COMPUTERNAME; nvidia-smi` → se não for Windows com a RTX, é nuvem.
- O Claude Code CLI (`claude`) ainda **não** está instalado no terminal do PC;
  o app desktop do Claude está instalado.

## Computador do Shiba
- Windows 11, RTX 5060 Ti 16 GB, Ryzen 5 5600GT, 32 GB RAM
- Python 3.12, FFmpeg
- Já usa: Adobe Premiere, After Effects, Photoshop, Media Encoder, Blender, CapCut
- **RTX 5060 Ti é Blackwell (sm_120): exige PyTorch com CUDA 12.8+ (wheels `cu128`).**
  Torch antigo falha com "no kernel image is available".
- Python 3.12 é novo para algumas ferramentas de áudio: usar um venv por ferramenta.

## Projetos musicais
### PROJETO 01 — CYBER POP PUNK
Músicas autorais: pop punk, glitch hop, dubstep, rock eletrônico, guitarras,
sintetizadores, vocais e drops.

### PROJETO 02 — CELESTIAL AMBIENT FUSION
Instrumentais (e às vezes vocais) para oração, meditação cristã, contemplação e louvor.
Ambient celestial, chill out, space ambient, pads, leads, sons da natureza,
harmonias worship, experimentos em 432 Hz.

### Músicas já feitas no Suno (assinatura encerrada)
Worship / pop rock cristão, vocal masculino em PT-BR com a voz do Shiba ("SHIBA My Voice"):
- BASTA - VTC Busca (Worship Ao Vivo) — 73 BPM, tinha stems no Suno Studio
- Quem Eu Sou de Verdade — 120 BPM
- Estrada de Volta — 110 BPM
- Luz que me alcança — 72 BPM, cinematic worship
Objetivo: recuperar o que ainda der para baixar e refazer stems/instrumentais localmente.

## Uso final
Músicas, stems, versões instrumentais e worship para usar nos **vídeos** do Shiba
(possivelmente monetizados → checar licença de cada modelo).

## Plano do estúdio local (gratuito)
| Função (antes no Suno) | Ferramenta local | Licença |
|---|---|---|
| Prompt + letra → música | ACE-Step 1.5 | Apache 2.0 (comercial ok) |
| Instrumental / ambient | ACE-Step + Stable Audio Open | SAO: comercial ok até US$ 1 mi/ano |
| Separar stems / tirar vocal | UVR5 (BS-/MelBand-Roformer) + Demucs 6 stems | Demucs: MIT |
| Voz do Shiba | RVC / Applio treinado com gravações dele | — |
| Edição e mix | DAW (REAPER, Cakewalk ou Waveform Free) | — |
| Master | Matchering | — |
| 432 Hz | FFmpeg / Rubber Band (−31,77 cents) | — |

**Não usar MusicGen (Meta) em vídeos monetizados:** pesos com licença não comercial.
Geração local com vocal ainda é inferior ao Suno; separação, instrumental e mix ficam iguais ou melhores.
Modelos: reservar ~30–50 GB de disco.

### Fases (cada uma precisa de autorização)
1. Auditoria local com `audit/audit-pc.ps1` (só leitura; relatório em `audit/output/`, fora do git).
2. Base: venv + PyTorch cu128 + UVR5 → stems e instrumentais.
3. Geração: ACE-Step 1.5 + Stable Audio Open.
4. Voz: RVC/Applio.
5. Mix e master: DAW + Matchering + script de 432 Hz.

## Contexto pessoal relevante
- O Shiba também usa o **Hermes** (agente de memória/automação, instalado no PC) para
  não precisar lembrar e copiar contexto entre chats. Este arquivo complementa o Hermes.
- Prioridade: economizar tempo dele. Menos perguntas, mais execução dentro do que foi autorizado.

## Status
- [x] Script de auditoria `audit/audit-pc.ps1` criado e revisado (seguro: só leitura,
      sem rede, grava apenas o relatório local).
- [ ] Abrir sessão local ("This computer") na pasta do repositório.
- [ ] Rodar a auditoria e registrar aqui o resumo.
- [ ] Baixar do Suno o que ainda estiver disponível.
