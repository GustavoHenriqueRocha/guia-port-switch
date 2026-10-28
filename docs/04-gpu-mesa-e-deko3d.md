# 4. GPU: Mesa/nouveau ou deko3d

Há dois caminhos para renderizar no Switch homebrew:

- **OpenGL pelo Mesa** (`switch-mesa` do devkitPro: Mesa 20.1 com o driver nouveau/nvc0 e um EGL próprio). É o caminho natural para um port que já tem backend OpenGL: o mesmo código compila para Linux e para o console.
- **deko3d**, a API nativa da GPU do Switch escrita por fincs (devkitPro). Fina, explícita (memória, command buffers, barreiras e sincronização ficam com você) e sem compilador de shader no console.

O port começou no Mesa, chegou perto de 60 FPS nele e depois ganhou um backend deko3d alternativo, escolhido em tempo de execução por um arquivo de configuração, com o GL sempre compilado como reserva.

## O que o Mesa 20.1 faz (e não faz) no Switch

Coisas que só se descobrem medindo ou lendo o driver:

- **O clear da janela bloqueia.** O EGL do Switch só chama `nwindowDequeueBuffer` (bloqueante) no primeiro clear ou desenho do framebuffer 0. Limpar a janela no começo do quadro trava a render thread esperando uma imagem livre **antes** de renderizar a cena em FBOs próprios. A correção foi adiar o clear da janela até o primeiro uso real (scanout, UI, fim do quadro). Uma etapa "clear" de 4–5 ms na CPU é espera, não trabalho.
- **ZCULL nunca liga** no nvc0 do 20.1 (o código está sob `#if 0`). Early-Z por pixel funciona, salvo com `discard`, `gl_FragDepth` ou escrita em imagem.
- **ETC2 não é hardware no GM20B.** O driver só anuncia ETC/ASTC para a classe 0xA297 (GK20A); o Switch é GM20B. "Usar ETC2 comprimido" passava por um fallback do st/mesa que alocava e decodificava na CPU da render thread. Conferir no binário o que `*_is_format_supported` aceita antes de assumir um formato.
- **Uniforms soltos são caros.** O nvc0 copia o bloco inteiro pela FIFO. Usar UBO e não reenviar bloco igual reduziu muito os comandos; enviar só o prefixo do bloco que o shader lê cortou os uniforms de 551 para 203 KB por quadro na área mais pesada.
- **O relógio de GPU não está em nanossegundos.** O `GL_TIMESTAMP` do switch-mesa avança cerca de 1,63 ns reais por "ns". Calibre contra o relógio da CPU por alguns segundos antes de usar.
- **O glthread existe, mas o EGL nunca o liga.** É preciso um patch para iniciá-lo (ver [capítulo 5](05-patches-do-mesa.md#0005-ligar-o-glthread)).

Mesa 26 também foi avaliado. Ele guarda o NIR inteiro de cada shader (6–8 MB por programa no console, contra 1,5 MB do 20.1), libera parte só se você fizer `glDetachShader` antes de `glDeleteShader`, e com cache frio trava mais. A 30 FPS com cache quente os dois empataram. O projeto ficou no 20.1 com patches.

## Por que tentar deko3d

Com a lógica do jogo otimizada, os picos de render passaram a dominar: a render thread gastava 3–4 ms por quadro só submetendo draws pelo Mesa. A meta era nenhum quadro acima de 16,7 ms, e o overhead do GL estava no caminho.

Resultado no mesmo roteiro de 44 áreas, mesmos clocks:

| Métrica | Mesa | deko3d |
|---|---:|---:|
| FPS médio | 58,89 | 59,23 |
| CPU da render thread | 34,3% | 20,5% |
| GPU ocupada por quadro | 8,5 ms | 8,7 ms |
| Áreas com FPS mínimo ≥ 59,9 | 3 | 12 |

A GPU ficou igual; o ganho foi CPU da render thread (−40%), que é o que sobra para absorver picos.

## Receita: trocar o GL por deko3d sem reescrever os shaders

O renderizador já gerava GLSL. A meta era usar **os mesmos textos** no deko3d.

**Shaders compilados no PC.** Não há compilador no console. O `uam` (do devkitPro) compila GLSL para DKSH offline e aceita o GLSL 4.3 que o backend GL já produzia, com `binding` explícito para UBOs e samplers. Os shaders vão num pacote só (ver [capítulo 6](06-cache-de-shaders.md#deko3d-tudo-pronto-no-pacote)).

**Convenções de coordenadas.** Crie o device com `DkDeviceFlags_DepthMinusOneToOne | DkDeviceFlags_OriginUpperLeft`. Para alvos fora da tela a memória fica igual à do GL, e viewport, scissor e blits valem 1:1. Só o desenho na imagem da janela inverte Y. Na versão 0.5.0 do deko3d, um viewport com altura negativa produz um scissor de hardware inválido (tela preta, sem erro). O que funcionou foi o swizzle de viewport `DkSwizzle_NegativeY`, que nega o Y no clip antes do viewport.

**Sentido de face.** Com a origem em cima, o winding se inverte na janela. Deixe uma chave em arquivo para inverter o cull sem rebuild: o primeiro teste no console mostrou o céu (uma cúpula vista por dentro) sendo descartado.

**Barreiras que o GL fazia sozinho.** Cópia de buffer para imagem antes do draw que a lê; alvo renderizado antes de um blit 2D; o próximo quadro voltando a escrever o alvo. Cada uma vira um `dkCmdBufBarrier` explícito.

**Atributo de vértice ausente.** No GL, um array desligado lê (0,0,0,1). No deko3d, crie um buffer constante de 16 bytes em memória com endereço de CPU (`DkMemBlockFlags_CpuUncached`) e ligue-o por instância. A memória de imagem sem flag `Cpu*` não tem endereço de CPU: o primeiro constante nunca tinha sido escrito.

**Tabelas de enum.** A ordem das operações lógicas (e de outros enums) do hardware de origem não é a do deko3d. Mapeie caso a caso, com teste de host.

## Bugs de deko3d que custaram dias

Os dois foram achados com a mesma técnica: ligar a `libdeko3dd` (build de debug, que diz a causa de um erro da fila), depois um modo "sync check" por arquivo que envia e espera cada operação e grava qual derrubou a fila.

- **Views montadas numa cópia local.** As image views eram preenchidas numa struct na pilha e copiadas para o mapa; o descritor apontava para lixo. Crash em `dkCmdBufBindRenderTargets`. Monte as views no objeto já guardado.
- **Command buffer escrevendo além do bloco.** Na 0.5.0, `dkCmdBufBindVtxBuffers` reserva 5 palavras por buffer e grava 6. Um `DkCmdBuf` de usuário não tem folga reservada: com 16 buffers perto do fim de um bloco de 64 KiB, as palavras extras caíam no começo do bloco seguinte e eram sobrescritas. A GPU rejeitava a lista ("GPU method error" com um valor que era claramente o cabeçalho de outro comando). Correção: 4 KiB livres depois de cada bloco de memória de comandos.

## Apresentação no deko3d

A libnx empresta uma imagem da janela por vez. Com `nwindowQueueBuffer` às vezes preso por 1,5 vblank, a render thread esperava a apresentação anterior. O que resolveu foi um **mailbox**: a render thread renderiza em três imagens próprias, e uma fila separada, numa thread de apresentação, faz dequeue, copia o quadro mais novo e faz queue. Quadro não copiado a tempo é descartado. Refreshes perdidos por janela de medição caíram de 1,05 para 0,53, e o maior acquire do render, de 61 ms para 0,004 ms.

Dois detalhes do mesmo trabalho: o log do backend era aberto, escrito e fechado na render thread, e gerava picos de 14–18 ms a cada 1800 quadros. Foi para uma fila com thread de serviço. E uma chamada IPC ao serviço de clock, feita na thread do jogo para o log, chegou a parar o jogo por 4,4 s; foi para uma thread própria.
