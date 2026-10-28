# 3. Threads, núcleos e prioridades no Horizon

O agendador do Horizon não se comporta como o do Linux. A primeira versão do port tinha uma render thread que "não rodava", e a explicação estava inteira aqui.

## As regras

1. **Só a prioridade 0x3B reveza tempo.** Em qualquer outra, uma thread ocupada impede as de prioridade igual ou menor **no mesmo núcleo** de rodar, mesmo que outros núcleos estejam ociosos.
2. **Uma thread com máscara de um núcleo nunca migra.**
3. O homebrew em modo aplicação usa os **núcleos 0, 1 e 2**; o 3 é do sistema.
4. Sem intervenção, a libnx cria toda thread no núcleo 0 com prioridade 0x3B. A render thread e a compilação de shaders só rodavam quando o jogo esperava.

(Prioridade menor = mais urgente: 0x2C passa na frente de 0x3B.)

## Um layout por papel

A solução foi classificar cada thread pelo papel e fixar núcleo e prioridade na criação, embrulhando `pthread_create` com `-Wl,--wrap=pthread_create`:

| Papel | Núcleo | Prioridade |
|---|---|---|
| Jogo (CPU do jogo, DSP, submissão de comandos) | 0, sozinho | 0x2C |
| Render thread | 2 | 0x2D |
| Worker que prepara os draws | 1 | 0x2E |
| Áudio (thread do host e a do SDL) | 1 | 0x2B |
| Serviços (log, cache do Mesa, carregadores) | 1 ou 2 | 0x3B |

```cpp
// Ilustrativo: o wrap decide núcleo/prioridade pelo papel que a thread anunciou.
extern "C" int __real_pthread_create(pthread_t*, const pthread_attr_t*, void*(*)(void*), void*);
extern "C" int __wrap_pthread_create(pthread_t* t, const pthread_attr_t* a,
                                     void*(*fn)(void*), void* arg) {
    Papel p = papel_pedido_pelo_chamador();             // padrão: Servico
    // iniciar_com_papel aplica svcSetThreadCoreMask/svcSetThreadPriority e depois chama fn(arg)
    return __real_pthread_create(t, a, iniciar_com_papel, embrulhar(fn, arg, p));
}
```

Pontos que fizeram diferença:

- **Toda thread não classificada vai para 0x3B.** Antes, threads de biblioteca nasciam na prioridade do jogo e preemptavam a render thread no mesmo núcleo.
- **Pilha mínima de 4 MiB** para threads criadas por bibliotecas: o padrão é pequeno para código gerado.
- **O log não pode bloquear o jogo.** A fila do log descarta a linha mais antiga quando enche, em vez de esperar.
- **O layout é escolhido por arquivo de configuração** (`fixed`, `float`, `legacy`), para A/B sem recompilar.

Resultado: com a render thread no seu próprio núcleo, cerca de 10 ms de GL por quadro saíram da thread do jogo. Como referência externa, o port SwitchWakerHD foi de 20 para 28 FPS só isolando o jogo num núcleo.

## O caso do SDL: `TIME_CRITICAL` abaixo do jogo

O SDL2 do devkitPro traduz `SDL_THREAD_PRIORITY_TIME_CRITICAL` para **0x3B**, a prioridade de revezamento, abaixo do jogo e da render thread. A thread de áudio do SDL, que deveria ser a mais urgente, ficava abaixo do jogo e de todo o resto, e o áudio picotava sempre que o núcleo estava ocupado. Detalhes e a issue reportada estão no [capítulo de áudio](10-audio.md#a-prioridade-time_critical-do-sdl).

## Sem espera ativa

O A57 não tem as instruções atômicas LSE, e cada atômico disputado custa caro. Regras adotadas:

- O pacer dorme com `svcSleepThread` até o prazo; não gira em laço. Se o `perf.txt` mostrar acordar atrasado (> 0,5 ms), há uma opção de girar os últimos N µs, desligada por padrão.
- Condition variable só é sinalizada quando alguém espera.
- Nada de atômico por draw. O port nfsmw-nx mediu 83 mil atômicos por quadro custando 1,1 ms.

## Contexto GL e threads

O contexto GL pertence à thread que o tornou atual. Ao mover o render para outra thread, o `MakeCurrent` precisa rodar **na** render thread (no projeto, por um comando enviado à fila dela). Sem isso, `glCreateShader` devolvia 0 sem erro visível.

O driver nouveau do Mesa 20.1 compartilha o push buffer entre contextos do mesmo share group **sem lock**. Compilar shaders num segundo contexto, em outra thread, travava o driver. O warm-up de shaders roda na própria render thread.

## Medir quem ocupa o quê

`svcGetInfo(InfoType_ThreadTickCount)` dá o tempo de CPU de cada thread por núcleo. Registrar isso por papel a cada janela de medição mostra na hora o gargalo: a thread do jogo a 95–98% no núcleo 0 significa que o limite é a lógica do jogo, e mexer na GPU não vai ajudar.
