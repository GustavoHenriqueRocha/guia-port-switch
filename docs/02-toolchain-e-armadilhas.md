# 2. Toolchain e armadilhas do Horizon

O homebrew de Switch é compilado com o **devkitA64** (GCC para AArch64) e a **libnx**, distribuídos pelo devkitPro via `pacman`. A saída é um `.nro`, aberto pelo Homebrew Menu. Para um port com SDL2 e OpenGL, os pacotes de partida são:

```sh
dkp-pacman -S switch-dev switch-sdl2 switch-mesa switch-glad switch-zlib
```

O CMake do devkitPro (`$DEVKITPRO/cmake/Switch.cmake`) serve como toolchain file. Com Ninja e ccache, o build incremental de um projeto grande fica em cerca de um minuto.

## O que muda em relação ao Linux

A libc é o **newlib**, não a glibc, e o sistema é o Horizon, não um Unix. Quase tudo compila igual, e por isso os problemas aparecem só em execução, às vezes só no console (o emulador esconde vários). Os que custaram mais tempo:

### `pthread_detach` não existe

O `pthread_detach` do newlib do devkitA64 retorna `ENOSYS`. Com isso, `std::thread::detach()` lança `std::system_error` ("Function not implemented"). O erro apareceu duas vezes no projeto, em threads diferentes, sempre como crash na primeira execução da thread.

Regra: no Switch, toda thread tem dono e termina com `join()`. Para uma thread que vive até o fim do processo, guarde o `std::thread` num objeto que nunca é destruído em vez de dar detach.

### `-ffast-math` na ligação quebra todas as exceções

Com `-ffast-math` no comando de **ligação**, o GCC acrescenta `crtfastmath.o` depois de `crtend.o`. O ld descarta o terminador do `.eh_frame` e **qualquer** exceção C++ aborta o processo. O sintoma é um crash na inicialização sem relação aparente com matemática.

No código recompilado há um segundo motivo para evitar fast-math: a VFP do 3DS tem semântica exata de flags (IXC, arredondamento, denormais). Com fast-math, cerca de 2 milhões de 86 milhões de checagens VFP divergiam. Os arquivos gerados usam `-fno-fast-math -ffp-contract=off`.

### TLS: `tpidr_el0` vale zero

A libnx encontra o TLS por uma função (`-mtp=soft`), mas partes da libgcc do devkitA64 leem o registrador `tpidr_el0` diretamente, e o Horizon o deixa em 0. Na prática isso aparece no **PGO**: o profiler de chamadas indiretas da libgcov usa variáveis `__thread`, e o build instrumentado caía no primeiro call indireto.

Correção: espelhar o ponteiro de TLS da libnx em `tpidr_el0` num construtor de alta prioridade e em toda thread nova (embrulhando `threadCreate` e `pthread_create` com `--wrap`):

```cpp
// Ilustrativo: o EL0 pode escrever tpidr_el0; a libnx expõe o TLS por armGetTls().
__attribute__((constructor(101)))
static void espelhar_tls() {
    void* tls = armGetTls();
    __asm__ volatile("msr tpidr_el0, %0" :: "r"(tls));
}
```

### Relógio: `cntpct_el0`, nunca `cntvct_el0`

O Horizon não libera o contador virtual no EL0: `mrs cntvct_el0` dá Data Abort na primeira leitura. Use `armGetSystemTick()` (que lê `cntpct_el0`, 19,2 MHz) e `armTicksToNs()`. Vale conferir no binário final:

```sh
aarch64-none-elf-objdump -d app.elf | grep -c cntvct_el0   # tem de dar 0
```

### Sistema de arquivos

O FS do Horizon não renomeia por cima de um arquivo existente. "Gravar em temporário e renomear" precisa remover o destino antes. E o cartão SD é lento para muitos arquivos pequenos: prefira poucos arquivos grandes (o cache de shaders do [capítulo 6](06-cache-de-shaders.md) é um arquivo só por isso).

## PGO com GCC no console

O código gerado de uma recompilação é grande e plano; o perfil de execução real ajuda o GCC a decidir inlining e layout. O fluxo que funcionou:

1. Build instrumentado com `-fprofile-generate=<dir no SD> -fprofile-update=single`, só nos arquivos quentes, ligando a libgcov (com o espelho de TLS acima).
2. Jogar cerca de 15 minutos nas cenas que importam, **com as mesmas configurações que o usuário vai usar**. O programa chama `__gcov_dump()` + `__gcov_reset()` a cada poucos minutos, porque um crash ou um fechamento pelo menu HOME perde o que não foi gravado.
3. Copiar os `.gcda` do SD e compilar com `-fprofile-use -fprofile-partial-training -Wno-missing-profile`.
4. Tolerar perfis desatualizados por função (`-Wno-error=coverage-mismatch`): uma função cujo CFG mudou só perde o perfil, em vez de quebrar o build. Conferir no log quantas perderam.

O perfil é invalidado por qualquer mudança que altere os corpos das funções quentes, por mudanças em headers inlinados nelas e por mudar o caminho do diretório de build (que entra no nome dos `.gcda`). Mudanças só no runtime do host (GL, áudio, threads) não invalidam.

## Tempo de compilação

Um recompilado tem milhares de funções distribuídas em centenas de arquivos. O que manteve o ciclo curto:

- **ccache** com `base_dir` e `hash_dir=false`, e o **mesmo diretório** de código gerado entre builds.
- **Distribuição estável de funções por arquivo**: uma estratégia que recalcula tudo do zero remaneja cerca de 30% dos arquivos a cada função nova; uma incremental, que preserva o arquivo de cada função existente, faz uma mudança tocar 0 ou 1 arquivo.
- **Funções gigantes sem os passes caros.** Em `-O3`, `sched1` e PRE dominavam os arquivos mais lentos. Marcar só as funções frias e enormes com `[[gnu::optimize("no-schedule-insns","no-gcse-after-reload")]]` levou a pior de 192 s para 88 s, sem afetar o perfil do PGO.
- **Não apagar `.ninja_log`/`.ninja_deps`** ao copiar um diretório de build: sem eles o Ninja recompila tudo. Antes de prometer um build rápido, estime com `ninja -n | wc -l`.
- Build pesado numa máquina dedicada, com limite de memória e de jobs; o notebook só para edição e builds incrementais.

## Emulador não é console

O Eden serve para smoke test de boot. Ele escondeu, neste port: o jogo rodando a meia velocidade, o contexto GL na thread errada e o `pthread_detach`. Para desempenho é pior ainda: o JIT varia 5–10% entre rodadas iguais, a primeira rodada de cada build é mais lenta e, com a janela escondida, o FPS cai a um terço. **Toda decisão de desempenho foi tomada com medição no console.**
