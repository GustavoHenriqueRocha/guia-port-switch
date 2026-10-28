# 8. Medição de frame time no console

Sem medição no console, todo o resto é palpite. Este capítulo descreve a instrumentação que guiou as decisões do port, com o custo de cada uma. Ela é toda ligada por arquivos vazios numa pasta `config/` no SD, para A/B sem recompilar.

## Log por janela

A cada 150 quadros o jogo grava uma linha num `perf.txt` com médias da janela:

- **Tempos por estágio** (ms por quadro): lógica do jogo, mixagem de áudio, submissão de comandos, render, apresentação, espera do pacer.
- **Clocks reais** de CPU, GPU e memória, e o modo (portátil/dock). Lidos uma vez por janela de um serviço de clock, em **outra** thread (uma chamada IPC na thread do jogo chegou a pará-lo por 4,4 s).
- **CPU por papel** de thread, por núcleo (`svcGetInfo(ThreadTickCount)`).
- **Memória**: arena do heap, pico, memória do processo, texturas e buffers vivos de GPU, falhas de memória de GPU.
- **Áudio**: taxa real do dispositivo, taxa de entrada, fila mínima e média, ocultações.
- **Pacing**: quadros de passo, intermediários, descartados; escala da DRS.

Um script lê o arquivo, separa sessões (uma nova sessão começa quando o contador de quadros volta a cair; o arquivo acumula execuções) e imprime um resumo com um **veredito de 60 FPS**: GPU e render thread ocupadas contra 16,7 ms, o par de passos contra 33,3 ms, e as travadas da sessão.

Cuidado: compare só a última sessão. Uma conta que misturou duas execuções deu 48 refreshes perdidos por janela num build que tinha 4.

## Log de picos

Médias de 150 quadros escondem os picos, e sem VRR o que importa é cada quadro que perde o refresh. Um segundo log grava **uma linha por quadro que perdeu o vsync**:

```text
spike t=… kind=step|interp|hold refreshes=2 expected=1 stage=guest|render|gpu|pacer
      guest_ms=… render_ms=… render_wait_ms=… gpu_ms=… top=<etapa> ctx=load,tex,shader
```

- **Culpa por estágio**, nesta ordem: o jogo passou do orçamento → a render thread (ocupada, sem as esperas) → a GPU (último resultado disponível, que atrasa 1–3 quadros) → o pacer (nada estourou: fase, deriva, acordar tarde).
- **Contexto**: troca de cena recente, textura nova, shader novo, falta de memória. Pico com `ctx=load` é carregamento e sai das contas de fluidez.
- **Sem custo no caminho quente**: por quadro, só uma struct POD num anel SPSC de 256 entradas, sem alocação; a formatação acontece em lote na janela, numa thread de serviço.

Um script agrupa os picos por área e por estágio, separa os isolados dos em sequência e diz quanto o quadro teria de encolher para caber. Foi ele que mostrou que mover o áudio para outro núcleo (1,7 ms) resolveria 3 de 95 picos de lógica, e a ideia foi descartada antes de ser implementada.

## Tempo de GPU sem travar

`GL_TIMESTAMP` com `glQueryCounter`, lido alguns quadros depois (nunca esperando o resultado), por etapa do quadro. Três cuidados, todos aprendidos no console:

1. **Calibrar o relógio.** No switch-mesa ele não está em nanossegundos; compare com a CPU por ≥ 3 s.
2. **Tirar as esperas.** Carimbos em volta de cada ponto em que a render thread bloqueia; o tempo ocupado é o span menos os buracos (ver [Espera não é custo](07-orcamento-e-pacing.md#espera-não-é-custo)).
3. **Flush entre carimbos.** Um carimbo só mede o que já foi entregue à GPU.

No deko3d, o equivalente são timestamps na fila: quatro por quadro (cena, espera do acquire, final, ocupado).

## Medir sem atrapalhar

Uma medição cara sai do caminho quente assim que responde a pergunta. Exemplos do port:

- Uma assinatura por draw (hash de uniforms e vértices) para estimar quantos draws poderiam ser juntados custava 3–4 ms por quadro. Respondeu "1%" e foi apagada, mas antes disso inflou as conclusões de vários testes.
- `mallinfo()` percorre o heap inteiro segurando o lock do malloc. Com uma lista corrompida, congela o processo sem crash. Foi trocado por uma varredura limitada dos bins, só sob demanda.
- O perfil por função da CPU do jogo custa ~190 ns por entrada de bloco e infla funções feitas de muitos blocos curtos. Desconte a sobrecarga antes de escolher o que otimizar.
- Com a instrumentação por função ligada, a lógica passou de ~12 para 39,5 ms por quadro e 97% dos quadros viraram "pico". O limite de um perfil de picos tem de ser relativo à média medida com o próprio perfil ligado.

## Tour por área

Uma área só não representa o jogo. O port tem um canal de laboratório: um roteiro JSON no SD, lido na abertura, com comandos de warp, espera, captura e controle (segurar o direcional, apertar botões). Um tour típico visita cerca de 45 áreas, cerca de 5 s cada, e um script casa as janelas do `perf.txt` com os comandos pelo contador de quadros e ordena as áreas por FPS e picos.

- O roteiro vai no SD **antes** da abertura: o FTP do menu de homebrew fecha quando o jogo abre.
- **Rode duas vezes.** A primeira passada mede compilação de shader; a segunda, o peso real.
- **Mexa o personagem.** Câmera parada mede uma cena que o jogador nunca vê.

## Protocolo de A/B

1. **Mesmo clock.** Com clock padrão a lógica chegava a ~17 ms por passo; com overclock ficava 30 FPS cravado com folga. O `perf.txt` grava o clock real em cada janela, e o script separa as sessões por clock.
2. Mesma cena, mesmo save, 2–3 minutos por modo, descartando as primeiras janelas.
3. Cache de shaders quente nas duas pontas.
4. Uma variável por vez, por arquivo de configuração.
5. Para lógica, olhar o tempo do jogo e a CPU do núcleo 0; para GPU, as etapas de GPU; para áudio, a taxa do dispositivo e as ocultações.

## Travamento sem crash report

Imagem parada, nada em `atmosphere/crash_reports`: não há pilha. A receita que funcionou:

1. **Marcadores baratos por thread**: um slot por papel com a etapa atual (store relaxed) e um contador de progresso por quadro.
2. **Thread vigia de prioridade mínima**, acordando a cada ~1 s. "Travado" = jogo ou render sem progresso por > 3 s com o app em foco, ignorando saltos do relógio (console em repouso).
3. **Gravar sem alocar**: a trava pode ser o lock do malloc. Buffer estático, formatação própria (o `printf` de float aloca no newlib), arquivo pela API de FS da libnx com flush.
4. **PC/LR das outras threads** com `svcSetThreadActivity` (pausar), `svcGetThreadContext3` e `svcQueryMemory` antes de cada leitura de pilha, se o NPDM permitir essas SVCs (teste com `envIsSyscallHinted`; SVC não permitida derruba o processo).
5. **Última chamada de serviço** com nome e ticks de início/fim em volta de cada IPC que pode bloquear.

E antes de concluir "crash": um `perf.txt` que parou também acontece quando o usuário fecha o jogo.

## Crash reports do Atmosphère

O `.nro` é carregado em endereço variável. Para achar a base, alinhe os endereços de retorno da pilha do relatório com instruções `bl`/`blr` do ELF: para a base certa, `retorno − base − 4` cai num `bl`/`blr` em quase todos os quadros. Depois, `aarch64-none-elf-addr2line -e app.elf` com `endereço − base`. Guarde o `.elf` exato de cada `.nro` enviado ao console.
