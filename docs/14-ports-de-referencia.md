# Ports de referência

Antes de começar um port, ou quando um gargalo aparece, vale olhar o que outros ports de Switch já fizeram. Este capítulo é o catálogo dos que foram lidos para este guia: o que cada um é, o que dá para reaproveitar e o que não vale copiar.

Como ler cada técnica:

- **medido aqui**: medido no console neste port;
- **número da fonte**: o número é do próprio port, não foi refeito aqui;
- **sem número**: a fonte não traz medida.

Além disso, cada técnica diz se **roda neste port** e se o ganho dela foi **medido isolado**. Uma técnica pode estar em uso sem número próprio, porque entrou junto com outras mudanças.

Ganho de outro jogo não se transfere: serve para escolher o que testar primeiro, não para prometer resultado. A última passada no catálogo foi em 25/11/2026.

## Recompilação de jogos de 3DS (o mesmo runtime deste guia)

### TriAevum (coccofresco)

[coccofresco/TriAevum](https://github.com/coccofresco/TriAevum). É a recompilação estática do Ocarina of Time 3D e do Majora's Mask 3D para PC (Vulkan/NRI), base de todos os ports abaixo.

- **Aproveitável:** o lado do renderer das correções de jogo. Superfícies produzidas pela GPU e lidas como textura (bloom em ping-pong); UI estendida para 16:9 com o clip Y comprimido; catálogo de warp por área para o tour automático.
- **Não copiar:** a free list do heap no host. Entrou num commit e foi revertida pelos próprios autores.

### MM3D-PC (Volpe34)

[Volpe34/MM3D-PC](https://github.com/Volpe34/MM3D-PC). Majora's Mask 3D no mesmo runtime, só para PC.

- **Ideia de pacing:** o passo do guest numa thread própria, com snapshot copy-on-write por página para o host. Sobrepõe o trabalho do host, mas não reduz o tempo do guest. Sem número.
- **IDs de diagnóstico só com flag:** o caminho de cada draw deixa de montar identidades que ninguém lê. Sem número.
- **Não copiar no Switch:** o VFP com float do host (só x86) e os caches de pipeline Vulkan.

### Ocarina-ReTuned (OTPR26)

[OTPR26/Ocarina-ReTuned](https://github.com/OTPR26/Ocarina-ReTuned). Fork do OoT3D com backend deko3d, validado só em emulador.

- **Aproveitável:** o hash do conteúdo da textura, em vez de reenviar a textura a cada uso (184 → 33 ms, número da fonte, em emulador). Este port já tinha a técnica.
- **Não copiar:** `dkFenceWait` a cada submit, que é pior que um anel de fences, e a compilação de GLSL no console. Pré-compile os shaders (capítulo 6).

### TriAevum-Switch, fork do John (JohnUzoka)

[JohnUzoka/TriAevum-Switch](https://github.com/JohnUzoka/TriAevum-Switch). OoT3D no Switch, derivado deste port.

- **Janela fastmem:** reserva plana do espaço do guest. Os acessos inline leem uma tabela de flags por página e vão direto à janela, sem percorrer a tabela de páginas. Estimativa da fonte: 7–10 %, "2–3 ms de 25–30 ms" por passo. Roda neste port; ganho isolado não medido.
- **Caminhos rápidos da thread do jogo:** despacho da lista PICA por tabela; snapshots de vértice e de textura com caminho de acerto; captura só do que mudou; LRU em O(1) no cache de geometria. Roda neste port, medido aqui: desligar essas chaves piorou o pico do guest numa área pesada de 14,9 para 19,4 ms.
- **Read-back com fence:** a cópia de textura que o jogo lê de volta vira fence + leitura adiada, no lugar da espera síncrona. Número da fonte, só nas cenas que leem de volta: 38,5 ms por cópia e 15 fps.
- **Não copiar:** o modo de desempenho por clkrst. Mexer no clock dentro do app briga com o sys-clk.

### mm3d-dekui, mm3dr e mm3d-practice-tools

[tgacquin/mm3d-dekui](https://github.com/tgacquin/mm3d-dekui), [Z3DR/mm3dr](https://github.com/Z3DR/mm3dr) e [PhlexPlexico/mm3d-practice-tools](https://github.com/PhlexPlexico/mm3d-practice-tools) são mods do Majora's Mask 3D, não ports.

- **Aproveitável:** a interface em 16:9 do dekui. Os headers do mm3dr dão os offsets das estruturas do jogo, e o warp do practice tools serviu de base para o tour automático por área (capítulo 8).
- **Desempenho:** nada. Nenhum dos três corta trabalho do jogo.

## Ports de Switch de outros jogos

### nfsmw-nx (StevensND)

[StevensND/nfsmw-nx](https://github.com/StevensND/nfsmw-nx). Need for Speed: Most Wanted (decomp) no Switch.

- **Flags de PGO:** `-fprofile-correction`, que aceita contadores inconsistentes de várias threads, e `-fno-profile-values`, que evita o perfil de chamada indireta. Esse perfil lê o `tpidr_el0`, que no Horizon é 0. Sem número; ainda não testado neste port.
- **LTO do GCC + ordem de funções** (`--section-ordering-file`): favorece o I-cache do A57. O link com LTO de uma base grande pede `-flto=2` mesmo com 16 GB.
- **Não copiar:** `nwindowSetSwapInterval(0)` e afinidade com máscara exclusiva, que a própria fonte mediu pior.

### Dusk by aleks (Twilight Princess)

[Alexgg1014/The-Legend-of-Zelda-Twilight-Princess-Alek-s-Ultimate-NX-Edition](https://github.com/Alexgg1014/The-Legend-of-Zelda-Twilight-Princess-Alek-s-Ultimate-NX-Edition) (CC0). Port de Switch do Dusklight (decomp do Twilight Princess), com deko3d via Aurora e shaders DKSH offline. O [HayatoG/dusklight](https://github.com/HayatoG/dusklight) é creditado só pela camada NVK original.

- **Nada deste port foi testado aqui ainda.**
- **malloc direto:** o newlib do devkitPro manda todo malloc acima de 31 B para `memalign(32)`, com até 2 frees extras sob o lock global. A técnica embrulha `malloc` e chama `_malloc_r` direto. Número da fonte só no conjunto de mudanças: +2 a +9 fps.
- **Swap interval 2 em 30 fps puro:** cadência de 2 vblanks constante, no lugar de pares 1v/3v.
- **Wake "quieto":** só sinalizar se o outro lado anunciou que vai dormir, porque no libnx todo notify vira `svcSignalProcessWideKey`. Sem número.
- **Amostrador de PC de ~1 ms** (`svcSetThreadActivity` + `svcGetThreadContext3`): mostrou que a thread principal deles passava ≈ 50 % do tempo esperando. Confira a espera antes de otimizar a CPU.
- **PGO:** as mesmas duas flags do nfsmw-nx.
- **Não copiar:** o "GPU Boost" (`apmSetPerformanceConfiguration`). A própria fonte diz que ele põe a CPU em 1020 MHz.

### SwitchWaker e SwitchWakerHD (centollOS)

[centollOS/SwitchWaker](https://github.com/centollOS/SwitchWaker) e [centollOS/SwitchWakerHD](https://github.com/centollOS/SwitchWakerHD). Já citados no capítulo 6 pelos patches de cache de shaders.

- **Quarto núcleo pelo forwarder** (NPDM com `highest_cpu_id=3`, máscara 0xF): tira a render thread ou o áudio dos núcleos 1–2. Exige forwarder ou NSP.
- **Swap interval 2 em 30 fps:** o mesmo do Dusk.
- **Staging com cache de CPU** (`DkMemBlockFlags_CpuCached` + flush): teste sintético 160,6 ms → 2,47 + 0,52 ms; no jogo real, nada (32,36 contra 32,47 ms), números da fonte. Só vale se o perfil mostrar escrita em memória sem cache.

### DS2_switch e ds2scholar-nx (Dark Souls II)

[XDASCATX/DS2_switch](https://github.com/XDASCATX/DS2_switch) e [KostinKD/ds2scholar-nx](https://github.com/KostinKD/ds2scholar-nx). Dark Souls II no Switch sobre Vulkan/NVK. O DS2_switch é o exemplo do capítulo 4 sobre quando trocar a API.

- **Aproveitável:** o quarto núcleo pelo forwarder, a mesma técnica do SwitchWakerHD.
- **Não copiar:** `appletSetCpuBoostMode` e o pipeline cache do Vulkan, que não se aplica ao deko3d.

### mesa-switch (danfromtico)

[danfromtico/mesa-switch](https://github.com/danfromtico/mesa-switch). Mesa com NVK para o Switch. É referência para quem fica no Vulkan; para um port em deko3d não traz técnica de desempenho.

## Como manter este catálogo

- Port lido entra aqui, com o commit consultado e a data. A técnica entra com o selo de número; o que não vale copiar entra com o motivo.
- Antes de um port novo, passe por esta lista e pelas [lições](13-licoes.md). Repo que não mudou desde a última passada não precisa ser relido.
