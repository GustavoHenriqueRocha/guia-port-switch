# 1. Introdução

Este guia mostra como levar um jogo que já roda como código nativo (uma recompilação estática de 3DS, ou um port de PC) para o Nintendo Switch como homebrew, e como fazê-lo rodar com **frame time estável**: nenhum quadro acima de 16,7 ms em jogo normal, não só "60 FPS de média".

Tudo aqui saiu de um port real e foi medido no console. Cada técnica vem com o problema que a motivou, o número que a justificou e, quando deu errado, o que se aprendeu.

## De onde vem

O caso de estudo é o **TriAevum**, uma recompilação estática (AOT) de *The Legend of Zelda: Ocarina of Time 3D*: o código ARM11 do 3DS é traduzido para C++ e compilado como programa nativo, sem interpretador. O recompilador, o runtime e o renderizador PICA → OpenGL são do projeto original, de **coccofresco** ([github.com/coccofresco/TriAevum](https://github.com/coccofresco/TriAevum)).

O trabalho descrito neste guia é o **port para o Switch** feito por Gustavo Henrique Rocha num fork ([TriAevum-Switch](https://github.com/GustavoHenriqueRocha/TriAevum-Switch)). A ideia central foi juntar num só lugar técnicas que já existiam espalhadas em outros ports de Switch e medir, uma a uma, o que realmente rodava bem neste jogo. Daí saíram:

- backend Switch (libnx, SDL2, Mesa/nouveau) e o backend **deko3d** alternativo;
- desempenho de CPU no console (PGO com GCC, layout de threads, ajustes do código gerado), a partir de técnicas usadas em outros ports;
- frame time: pacing, interpolação a 60 Hz, resolução dinâmica, medição por pico;
- áudio no Switch (audren, reamostrador, thread própria);
- ferramentas de medição e a suíte de testes de regressão.

Outras referências usadas e citadas nos capítulos: os patches de cache de shaders do **SwitchWaker** (centollOS) e do **SwitchWakerHD**, as medições publicadas pelo port **nfsmw-nx**, e o deko3d/uam de **fincs** (devkitPro).

## O que este guia não cobre

- Nada sobre obter jogos, ROMs, chaves ou firmware, nem sobre contornar proteções. O ponto de partida é um programa que você já tem o direito de compilar e rodar.
- Nenhum asset de jogo. Os trechos de código são curtos, escritos para ilustrar a técnica; não são cópia do projeto.
- A recompilação em si (descoberta de funções, geração de C++) aparece só onde afeta o desempenho no console.

## Como ler

Os capítulos seguem a ordem em que os problemas aparecem num port:

| Capítulo | Pergunta que responde |
|---|---|
| [2. Toolchain](02-toolchain-e-armadilhas.md) | O que quebra só no Horizon e como compilar rápido o bastante |
| [3. Threads](03-threads-no-horizon.md) | Por que a render thread não roda mesmo com núcleos livres |
| [4. GPU](04-gpu-mesa-e-deko3d.md) | Mesa/nouveau ou deko3d, e o que cada um custa |
| [5. Patches do Mesa](05-patches-do-mesa.md) | O que foi preciso mudar no driver e por quê |
| [6. Cache de shaders](06-cache-de-shaders.md) | Como não compilar shader durante o jogo |
| [7. Orçamento e pacing](07-orcamento-e-pacing.md) | Como caber em 16,7 ms e entregar um quadro por refresh |
| [8. Medição](08-medicao-de-frame-time.md) | Como saber, no console, qual quadro estourou e por quê |
| [9. Memória](09-memoria.md) | Heap do newlib, memória de GPU e sessões longas |
| [10. Áudio](10-audio.md) | Áudio sem chiado e os dois bugs reportados ao devkitPro |
| [11. Deploy](11-deploy.md) | Levar o `.nro` ao console e trazer os logs de volta |
| [12. Testes](12-testes-de-regressao.md) | Como impedir que um bug do console volte |
| [13. Lições](13-licoes.md) | O resumo, para consultar antes do próximo port |

## Hardware de referência

Os números citados são do Switch (Tegra X1): quatro Cortex-A57, dos quais o homebrew usa três; GPU Maxwell GM20B; memória compartilhada entre CPU e GPU. Quando um número depende do clock, o capítulo diz qual. Comparar desempenho só faz sentido com o mesmo clock (ver [Medição](08-medicao-de-frame-time.md#protocolo-de-ab)).
