# 5. Patches do Mesa

O `switch-mesa` do devkitPro é o Mesa 20.1 com três patches de plataforma. Para ter cache de shaders em disco e glthread, o port reconstruiu esse pacote com sete patches por cima, compilados no host com o devkitA64 e a libnx instalados, sem tocar na instalação do devkitPro (o resultado vai para um prefixo próprio e substitui as bibliotecas na ligação).

**Origem.** Os patches 0001 a 0006 são adaptações dos patches de cache de shaders e glthread do **SwitchWaker** (centollOS) e do **SwitchWakerHD**. O 0007 é deste port. Este capítulo explica o porquê de cada um; o código está nos projetos de origem.

| Patch | O que faz | Entra na identidade do cache? |
|---|---|---|
| 0001 | compatibilidade do `timespec_get` com o newlib novo | sim |
| 0002 | contadores e tempos de compilação | sim |
| 0003 | cache de shaders em disco no Horizon, num arquivo só | sim |
| 0004 | código de máquina do nvc0 também no cache | sim |
| 0005 | função para ligar o glthread | não |
| 0006 | uploads de textura por PBO assíncronos no glthread | não |
| 0007 | `thrd_success` vale 4 no newlib | não |

A última coluna importa porque o cache identifica o build do driver por um hash do fonte e dos patches. Os patches que não mudam nenhum código de shader compilado (0005 a 0007) ficam fora desse hash, para não invalidar o cache dos usuários a cada ajuste.

## 0001: `timespec_get`

O newlib do devkitA64 r29 **declara** `timespec_get()` sem fornecê-la, e o fallback estático do Mesa em `include/c11/threads.h` colidia com a declaração. O patch só renomeia o fallback (`mesa_timespec_get`). Nenhuma mudança de comportamento: é o que permite compilar o Mesa 20.1 com o toolchain atual.

## 0002: onde vai o tempo de compilação

Antes de otimizar a compilação de shaders é preciso saber em que etapa o tempo vai. O patch acrescenta um header público, `mesa_switch.h`, com uma função que devolve contadores e tempos de:

- `glCompileShader` (e quantos o cache permitiu adiar);
- `glLinkProgram`, separado entre o linker GLSL e o `LinkShader` do state tracker (GLSL IR → TGSI);
- `nvc0_program_translate` (TGSI → código de máquina);
- `glProgramBinary`/`glGetProgramBinary`;
- leituras e escritas do cache em disco (preenchidas pelo 0003).

O jogo grava esses números no log de desempenho. Foi assim que se viu que um shader novo custava de 1 a 3 s no console, e que o tempo estava na tradução do nvc0, não só no GLSL.

## 0003: cache em disco num arquivo só

O cache em disco do Mesa (`disk_cache.c`) é desligado no Horizon pelo próprio devkitPro, por bons motivos: ele usa `mmap`, `flock`, `getpwuid`, um arquivo por entrada e zlib. O newlib do Horizon não tem os três primeiros, e o SD é lento para abrir milhares de arquivos pequenos.

O patch acrescenta um backend próprio com a mesma API:

- **Um arquivo só, só de acréscimo** (`$MESA_SHADER_CACHE_DIR/mesa_shader_cache.bin`), com CRC por entrada; entrada velha ou danificada é descartada na leitura.
- **Um índice ao lado**, para abrir o cache com uma leitura em vez de uma por registro (índice ausente ou danificado é reconstruído a partir dos registros).
- **Manutenção fora do caminho do jogo**: uma thread poda entradas não usadas há várias execuções, uma vez por execução.
- **Identidade do driver** por um hash gerado no build (fonte + patches), porque no Horizon não há `dladdr` nem build-id. Cache escrito por outro build do driver nunca é lido.

Com o cache, um shader já visto carrega em cerca de 12 ms em vez de 1–3 s. A variável `MESA_SHADER_CACHE_DIR` precisa estar definida **antes** de o SDL criar o contexto GL.

## 0004: código de máquina do nvc0 no cache

O 0003 guarda o resultado do GLSL. A tradução TGSI → código de máquina do nvc0 continuava rodando. O Mesa 20.3 ganhou um cache para isso depois de reorganizar estruturas internas; o patch é um equivalente menor para o 20.1:

- `nvc0_program_translate` procura o programa traduzido (código, cabeçalho, relocações, fixups) por uma chave das entradas (chipset, estágio, tokens TGSI, clip planes, memória compartilhada) antes de rodar o `nv50_ir`.
- Os fixups guardam **ponteiros de função**, que mudam de execução para execução. O patch os grava como **índices** na tabela do emissor GM107, o único compilado no build do Switch. Programas com outros fixups, compute e stream output não são cacheados.

## 0005: ligar o glthread

O Mesa tem o **glthread**: as chamadas GL são enfileiradas e executadas por uma thread do driver, e a thread que chama o GL volta logo. O EGL do switch-mesa **nunca o inicia** e deixa vazio o gancho que nomeia a thread de trabalho.

O patch acrescenta `mesa_switch_glthread_start()`, chamada pela aplicação com o contexto atual. A aplicação passa o próprio gancho, que nomeia a thread e aplica núcleo e prioridade conforme o [layout de threads](03-threads-no-horizon.md). Sem a chamada, o patch é inerte.

## 0006: uploads de textura assíncronos

No 20.1, todo `glTexSubImage*`/`glCompressedTexSubImage*` fazia o glthread **esperar** a fila inteira esvaziar antes da chamada. Numa troca de área, com dezenas de texturas novas, a render thread engasgava exatamente quando já estava mais carregada.

O patch faz o que o Mesa 20.3 faz: upload a partir de um **pixel unpack buffer** (PBO) entra na fila como qualquer comando, porque o "ponteiro" é só um offset no buffer. Upload a partir da memória do cliente continua síncrono, como deve. Para isso, o glthread passa a acompanhar o `GL_PIXEL_UNPACK_BUFFER` ligado e os buffers apagados.

Junto com o glthread, o port também tirou o `glGetError` por textura (cada um força uma sincronização) e passou a ler o erro de falta de memória uma vez, ao drenar a fila antes do swap.

## 0007: `thrd_success` vale 4 no newlib

Este bug foi relatado ao devkitPro (pacman-packages) em outubro de 2026; a issue foi removida pelos mantenedores sem resposta, e a correção fica registrada aqui.

O C11 não fixa os valores de `thrd_success` e companhia. O newlib define `thrd_success` como **4**. O `u_thread_create` do Mesa testava `if (ret)`, ou seja, tratava qualquer valor diferente de zero como falha:

```c
/* Antes: sucesso do newlib (4) lido como falha. */
ret = thrd_create(&thread, routine, param);
if (ret)
    return 0;

/* Depois: aceita o valor certo, e 0 para quem embrulha thrd_create. */
if (ret != thrd_success && ret != 0)
    return 0;
```

Consequência: a thread era criada e estava **rodando**, mas o Mesa achava que não, liberava a fila debaixo dela e seguia sem glthread. O sintoma era o glthread simplesmente não ligar, sem erro, com uma thread órfã usando memória já liberada. O mesmo teste aparecia na thread de manutenção do cache do 0003, que podia sobreviver ao mutex que usava.

A lição é geral: **nunca compare um código de retorno C11 com zero**; compare com a constante. E um port para newlib deve procurar `if (thrd_create(...))` e `== 0` em todas as dependências.
