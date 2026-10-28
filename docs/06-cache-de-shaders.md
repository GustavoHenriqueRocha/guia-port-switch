# 6. Cache de shaders

Compilar um shader no Switch custa de 1 a 3 segundos no Mesa. Um único shader novo durante o jogo é uma travada visível; numa troca de área com dezenas deles, o jogo para. O objetivo deste capítulo é chegar a **zero compilações durante o jogo**.

## Três camadas

1. **Cache do driver em disco** (patches 0003/0004 do [capítulo 5](05-patches-do-mesa.md)): um shader já visto carrega em cerca de 12 ms.
2. **Warm-up na abertura**: o próprio jogo guarda no SD a fonte de cada shader que já gerou e, ao abrir, compila todos antes do primeiro quadro. Com o cache do driver quente, 269 shaders levaram 2,3 s.
3. **Cache pronto no pacote**: o usuário recebe o cache já preenchido.

Na primeira passada por uma área sem cache, ela rodava a 11,7 FPS; com o cache quente, a 44 (antes das otimizações de GPU). É a diferença entre "injogável" e "medível".

## O warm-up roda na render thread

A ideia óbvia, compilar num contexto compartilhado em outra thread, travou o nvc0: contextos do mesmo share group usam o mesmo push buffer sem lock (ver [threads](03-threads-no-horizon.md#contexto-gl-e-threads)). O warm-up é síncrono, na render thread, antes do primeiro quadro, com uma tela de carregamento.

## O cache pode ir no pacote

A chave do cache do Mesa é o build do driver + o chip + o texto do shader. Nada ali depende do aparelho. Então o cache gerado num console vale para qualquer outro com o mesmo build:

1. Passar por todas as áreas do jogo (no projeto, um roteiro automático de warps; ver [Medição](08-medicao-de-frame-time.md#tour-por-área)). As fontes dos shaders se acumulam no SD.
2. Juntar as fontes de várias sessões (união dos arquivos).
3. Abrir o jogo uma vez: o warm-up compila tudo e o driver grava o cache.
4. Copiar as duas pastas, fontes e cache do driver, para o pacote distribuído.
5. Conferir no arquivo de status do warm-up: nenhum shader pulado e tempo baixo.

## deko3d: tudo pronto no pacote

O deko3d não tem compilador no console, então o cache deixa de ser otimização e vira requisito. O backend usa as **mesmas fontes** que o GL grava no SD:

- Cada estágio é identificado por um hash (FNV-1a de 64 bits) do texto GLSL final, o mesmo que o GL compilaria.
- Um script no PC chama o `uam` para cada fonte e junta tudo num arquivo `deko3d.pack` (272 estágios em cerca de 6 s).
- No console, o DKSH inteiro vai para memória de código (`DkMemBlockFlags_Code`, alinhamento de 256 bytes) e é carregado com `dkShaderMakerDefaults`.

### Nunca compilar, nunca pular em silêncio

Um shader que não está no pacote não pode virar uma travada nem um objeto invisível. A solução foi ter sempre um **programa paramétrico** ("uber shader") de reserva:

- O pacote inclui desde o início quatro variantes genéricas (com/sem iluminação × dois formatos de textura).
- Todo draw chega com o programa especializado **e** o paramétrico. Com o DKSH do especializado, renderiza com ele; sem, renderiza com o paramétrico; sem os dois, pula e conta.
- A fonte que faltou é gravada no SD e entra no próximo pacote. Cada fonte é resolvida uma vez por execução, e a ausência também fica lembrada; senão um draw sem DKSH refaria a busca (e uma tradução de ~31 KB de texto) a cada quadro.

### Shaders internos

Os shaders do próprio backend (scanout, UI) também são GLSL compilados pelo `uam` no PC e embutidos num header como `uint8_t[]`. Detalhe: o `uam` não aceita uniform solto; use um bloco std140.

## Checklist

- O diretório do cache é definido antes de criar o contexto.
- O status do warm-up aparece no log (quantos, quanto tempo, quantos pulados).
- O log de desempenho conta compilações por janela; qualquer compilação fora de carregamento é bug.
- Um pico de frame time registra se houve shader novo naquele quadro (ver [Medição](08-medicao-de-frame-time.md#log-de-picos)).
- O pacote distribuído traz o cache gerado com o mesmo build do driver.
