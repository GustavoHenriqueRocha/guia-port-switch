# 10. Áudio no Switch

O áudio foi a primeira coisa a denunciar problemas de agendamento: chiado, picotes e uma fila que crescia até descartar. Os ajustes deste capítulo levaram a um áudio limpo em sessões longas, e dois deles viraram bugs reportados ao devkitPro.

## Como o SDL2 do devkitPro toca

O backend de áudio do SDL2 no Switch usa o **audren** (o renderizador de áudio do sistema). Comportamentos que importam:

- **Não reamostra.** O `spec.freq` pedido vai direto ao audren; a hint de reamostragem do SDL não tem efeito.
- Usa só **2 wave buffers** e espera, em quadros de 5 ms, que o recém-enfileirado comece a tocar.
- Com buffers pequenos a voz passa fome (chiado), e com a thread de áudio atrasada a fila cresce até descartar.

## Saída a 48 kHz com reamostrador próprio

O áudio do jogo de origem roda a cerca de 32,7 kHz. Em vez de pedir essa taxa ao audren, o port:

- abre o dispositivo a **48.000 Hz** e reamostra no próprio jogo, com um filtro sinc-Kaiser polifásico (ganho DC unitário por fase, saturação em s16);
- usa um ajuste fino de taxa de ±0,5% para manter a fila no nível certo, em vez de inserir ou cortar amostras;
- usa buffer de dispositivo de **1024 quadros** (configurável de 256 a 4096).

## Uma thread de áudio do host

A mixagem do jogo (o DSP emulado) é sequencial com a lógica e fica na thread do jogo. O lado do host foi para uma thread própria, no núcleo 1, prioridade 0x2B, acordada a cada envio e a cada 4 ms. Ela:

- faz **time-stretch** por períodos de pitch só quando a fila está quase vazia ou há lentidão sustentada;
- faz **ocultação** (repete o último período com fade) quando o jogo atrasa, em vez de deixar o buraco virar estalo.

Lição do stretch: a primeira versão usava um crédito com sinal e editava o áudio o tempo todo; em 26 minutos inseriu 153 s e removeu 346 s. Corrigida, uma simulação de 30 minutos a velocidade normal edita 264 ms (0,015%). Esse tipo de erro só aparece em minutos de jogo, e por isso a simulação longa virou teste.

## A prioridade `TIME_CRITICAL` do SDL

Relatado ao devkitPro (SDL) em outubro de 2026; a issue foi removida pelos mantenedores sem resposta, e a correção fica registrada aqui.

O SDL cria a thread de áudio com `SDL_THREAD_PRIORITY_TIME_CRITICAL`. No port do devkitPro, essa prioridade é traduzida para **0x3B** no Horizon, que é a prioridade de revezamento, abaixo de qualquer thread de jogo (0x2C) ou de render. Pelas [regras do agendador](03-threads-no-horizon.md#as-regras), uma thread ocupada de prioridade mais alta no mesmo núcleo impede a de áudio de rodar. Resultado: o áudio picotava exatamente nos momentos de carga.

Contorno no port, enquanto a correção não chega ao pacote: embrulhar a função na ligação e aplicar a prioridade certa.

```cpp
// Ligação: -Wl,--wrap=SDL_SetThreadPriority
extern "C" int __real_SDL_SetThreadPriority(SDL_ThreadPriority p);
extern "C" int __wrap_SDL_SetThreadPriority(SDL_ThreadPriority p) {
    if (p == SDL_THREAD_PRIORITY_TIME_CRITICAL)   // a thread de áudio do SDL
        return R_SUCCEEDED(svcSetThreadPriority(CUR_THREAD_HANDLE, 0x2B)) ? 0 : -1;
    return __real_SDL_SetThreadPriority(p);
}
```

0x2B fica acima do jogo, e a thread de áudio passa quase todo o tempo esperando o audren, então não rouba CPU de ninguém.

## `thrd_success` vale 4 no newlib

Relatado ao devkitPro (pacman-packages) em outubro de 2026, com o mesmo destino da issue do SDL.

O newlib define `thrd_success` como 4. Código que testa `if (thrd_create(...))` ou `== 0` trata uma thread criada com sucesso como falha. No Mesa, isso fazia o glthread não ligar e liberar estruturas usadas pela thread que já rodava. A análise completa está no [capítulo 5](05-patches-do-mesa.md#0007-thrd_success-vale-4-no-newlib).

Está neste capítulo porque o mesmo padrão aparece em qualquer biblioteca de áudio ou de threads portada para o Switch que use `<threads.h>`. Ao portar uma dependência, procure `thrd_create`, `mtx_init`, `cnd_init` e compare sempre com a constante.

## Mixagem mais barata, bit a bit igual

A mixagem do DSP emulado foi reescrita para custar menos sem mudar uma amostra: 0,0506 → 0,0288 ms por quadro de DSP no host (−43%). A prova é um digest do áudio produzido, igual no x86-64 e no AArch64 (rodado no qemu), contra a versão original.

## Áudio depois da apresentação

A análise de picos mostrou quadros em que a lógica, somada à mixagem, passava do orçamento. Os quadros do DSP (mixagem e thread de som) passaram a rodar **depois** da apresentação do quadro, e na espera da render thread quando os slots estão cheios. Isso não diminui o trabalho; muda quando ele acontece, para fora da janela em que um atraso vira refresh perdido.

## Diagnóstico

- Linha `audio:` no log de desempenho: taxa real do dispositivo (~48.000), taxa de entrada (~32.728 a velocidade normal), fila mínima e média, milissegundos inseridos, removidos e ocultados.
- Um arquivo de configuração grava 60 s do áudio de saída num WAV no SD, para ouvir no PC o que o console tocou.
