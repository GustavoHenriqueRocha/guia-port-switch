# 13. Lições

O resumo do guia, para reler antes do próximo port. Cada item aponta para o capítulo com o contexto.

## Plataforma

1. **O emulador esconde bugs do console**: meia velocidade, contexto GL na thread errada, `pthread_detach`. Smoke test no emulador, decisão no console. ([2](02-toolchain-e-armadilhas.md#emulador-não-é-console))
2. **`-ffast-math` na ligação quebra todas as exceções C++.** ([2](02-toolchain-e-armadilhas.md#-ffast-math-na-ligação-quebra-todas-as-exceções))
3. **`pthread_detach` retorna `ENOSYS`.** Toda thread tem dono e termina com `join()`. ([2](02-toolchain-e-armadilhas.md#pthread_detach-não-existe))
4. **`tpidr_el0` vale zero.** Espelhe o TLS da libnx se algo da libgcc for usado (PGO). ([2](02-toolchain-e-armadilhas.md#tls-tpidr_el0-vale-zero))
5. **`cntpct_el0`, nunca `cntvct_el0`.** Guarda no código e no ELF. ([2](02-toolchain-e-armadilhas.md#relógio-cntpct_el0-nunca-cntvct_el0))
6. **`thrd_success` vale 4 no newlib.** Compare com a constante, nunca com zero. ([5](05-patches-do-mesa.md#0007-thrd_success-vale-4-no-newlib))

## Threads

7. **Prioridade igual não reveza no Horizon** (só 0x3B reveza). Classifique cada thread por papel e fixe núcleo e prioridade. ([3](03-threads-no-horizon.md#as-regras))
8. **`TIME_CRITICAL` do SDL vira 0x3B**, abaixo do jogo: embrulhe e corrija. ([10](10-audio.md#a-prioridade-time_critical-do-sdl))
9. **Contexto GL só na thread que o tornou atual**, e o nvc0 não tem lock no push buffer compartilhado: warm-up de shaders na render thread. ([3](03-threads-no-horizon.md#contexto-gl-e-threads))

## GPU e shaders

10. **Etapa "clear" cara é espera, não trabalho.** O EGL do Switch faz o dequeue no primeiro uso da janela; adie o clear. ([4](04-gpu-mesa-e-deko3d.md#o-que-o-mesa-201-faz-e-não-faz-no-switch))
11. **Confira no binário o que o driver suporta.** ETC2 "aceito" era decodificação na CPU. ([4](04-gpu-mesa-e-deko3d.md#o-que-o-mesa-201-faz-e-não-faz-no-switch))
12. **Zero compilações durante o jogo**: cache do driver em disco, warm-up, cache no pacote; no deko3d, pacote DKSH com programa paramétrico de reserva. ([6](06-cache-de-shaders.md))
13. **O tamanho declarado de um UBO é contrato de layout, não o que o shader lê.** Meça no corpus real antes de prometer economia. ([4](04-gpu-mesa-e-deko3d.md#o-que-o-mesa-201-faz-e-não-faz-no-switch))
14. **Num backend explícito, leia o que a biblioteca escreve.** Um command buffer sem folga e views montadas na pilha custaram dias; a build de debug da biblioteca e um modo "sync check" acharam os dois. ([4](04-gpu-mesa-e-deko3d.md#bugs-de-deko3d-que-custaram-dias))

## Frame time

15. **Meça picos, não médias.** Sem VRR, cada refresh perdido é visível. Um log por quadro que estourou, com o estágio culpado. ([8](08-medicao-de-frame-time.md#log-de-picos))
16. **Custo para decidir é tempo ocupado; espera nunca entra.** Uma medida que inclui bloqueio cresce quando há folga, e a política que corta trabalho por ela se trava. ([7](07-orcamento-e-pacing.md#espera-não-é-custo))
17. **Tirar uma medida inflada pode expor que o orçamento nunca foi o que parecia.** Calibre a margem no console. ([7](07-orcamento-e-pacing.md#margem-calibrada))
18. **Dois relógios "de 60 Hz" nunca são o mesmo relógio.** Quem apresenta segue quem exibe. ([7](07-orcamento-e-pacing.md#o-pacer-e-o-relógio-do-display))
19. **Dois controladores sobre o mesmo recurso decidem com a mesma medida.** ([7](07-orcamento-e-pacing.md#resolução-dinâmica-drs))
20. **Todo "aplica em X" ganha contador de X.** A DRS passou um teste inteiro "mudando" uma escala que nunca era aplicada; o contador de aplicação mostrou na primeira medida.
21. **Otimização "tudo ou nada" precisa de contador de motivo desde a primeira versão.** Senão, quando ela não age, só resta adivinhar.
22. **Se um defeito visual some a 30 FPS, comece pela interpolação.** ([7](07-orcamento-e-pacing.md#interpolação-e-culling))

## Memória

23. **Nada de alocação grande por quadro**; o heap do newlib tem lock global e fragmenta. ([9](09-memoria.md#o-heap-do-newlib))
24. **Cache de GPU sem orçamento é crash em minutos.** ([9](09-memoria.md#memória-de-gpu-limitada))
25. **Crash dentro do driver não acusa o chamador.** Struct com ponteiro ímpar é memória sobrescrita; prove a sua parte com ASan. ([9](09-memoria.md#heap-corrompido-o-crash-não-acusa-o-culpado))
26. **Antes de mudar quem guarda um struct grande, veja quais campos alguém lê.** ([9](09-memoria.md#structs-grandes-custam-banda))
27. **Mais folga entre threads não é só um número**: estado compartilhado pode supor o contrário. ([7](07-orcamento-e-pacing.md#quadros-em-voo))

## Processo

28. **Uma variável por vez, mesmo clock, cache quente, várias áreas, duas passadas.** ([8](08-medicao-de-frame-time.md#protocolo-de-ab))
29. **Uma medição cara sai do caminho quente assim que responde a pergunta.** ([8](08-medicao-de-frame-time.md#medir-sem-atrapalhar))
30. **Os logs antigos já dizem muito.** Antes de pedir uma rodada nova, passe o script nos logs que existem.
31. **Todo bug ganha teste de host; toda decisão medida ganha guarda.** ([12](12-testes-de-regressao.md))
32. **Mudança que roda o tempo todo precisa de teste de longa duração** antes de ir ao console. ([9](09-memoria.md#teste-de-longa-duração))
