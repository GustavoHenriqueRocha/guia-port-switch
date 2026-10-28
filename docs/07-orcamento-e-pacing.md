# 7. Orçamento de 16,7 ms e pacing

A tela do Switch atualiza a ~60 Hz e não tem VRR. Cada refresh sem imagem nova é uma travada visível, e uma média de 59 FPS pode esconder dezenas delas por minuto. Por isso o objetivo do port foi **frame time**: cada quadro dentro de 16,7 ms, um quadro novo por refresh.

## O orçamento

Para 60 Hz, cada quadro tem 16,7 ms em **cada** estágio do pipeline, que roda em paralelo:

```text
núcleo 0  [ jogo: lógica + submissão ]──┐
núcleo 2                                └─[ render thread: draws, uploads ]──┐
GPU                                                                          └─[ GPU ]──▶ tela
```

Cada estágio pode ocupar até 16,7 ms, desde que nenhum passe disso. O primeiro que estoura define o quadro. Saber **qual** estourou é o assunto do [capítulo 8](08-medicao-de-frame-time.md).

## Lógica a 30, imagem a 60

Muitos jogos de 3DS rodam a lógica a 30 passos por segundo. Duas consequências:

- **Velocidade.** Se o jogo avança um passo a cada dois refreshes, apresentar a 30 Hz com limite de um refresh por apresentação faz o jogo rodar a meia velocidade. O emulador escondia isso; no console era óbvio.
- **60 FPS por interpolação.** Para mostrar 60 imagens por segundo, o port renderiza um quadro intermediário entre dois passos, interpolando as transformações. O par passo + intermediário precisa caber em 33,3 ms.

### Interpolação e culling

O jogo corta a geometria com a câmera **de cada passo**, então o conjunto de draws muda entre dois passos. Regras que eliminaram uma piscada ao girar a câmera:

1. O quadro no instante de um passo é **aquele passo exatamente**, não uma amostra em alpha 0 sobre a lista do passo seguinte.
2. Draw sem par não pode ser renderizado com a câmera de um só passo. Meça o movimento de câmera nos draws pareados estáticos e aplique-o nos sem par.

Se um defeito visual some a 30 FPS, comece pela interpolação.

## O governador

Quando o par não cabe, renderizar o intermediário atrasa o próximo passo e a travada é pior. Um **governador** decide por quadro: renderizar o intermediário cheio, numa resolução menor, ou descartá-lo.

- Começa cheio, só desce com medição real (3 decisões seguidas acima do orçamento) e sobe quando volta a caber em 97%, com sondas periódicas.
- **Decide com tempo ocupado, nunca com tempo de parede.** Esta foi a lição mais cara do port (abaixo).

### Espera não é custo

O tempo de GPU de um quadro era medido de um carimbo no início a outro no fim. No meio, a render thread bloqueava esperando uma imagem livre da janela, e a GPU ficava ociosa. O span incluía esse buraco: o governador via 18,5 ms por passo quando o trabalho real era 12,3 ms, e descartava 74 de 75 intermediários. O contador de FPS dizia ~60; na tela eram 30 imagens distintas, cada uma repetida.

Pior: cortar trabalho **não reduz a espera** (um quadro mais barato só espera mais), então a medida inflada se sustentava sozinha.

Correção: carimbos de GPU antes e depois da espera, e a espera da CPU medida no próprio gancho do acquire e subtraída. E um detalhe de GL: um `glQueryCounter` emitido depois do último `glFlush` só executa no próximo flush. Carimbos "antes" e "depois" de uma espera, sem flush entre eles, saem iguais. Confira em que flush cada carimbo sai.

### Margem calibrada

Tirar a espera expôs outro fato: com a GPU perto de 100%, ela não é alimentada de ponta a ponta. Pares medidos de 29–30 ms "cabiam" em 33,3 e mesmo assim perdiam o refresh; o modelo reproduziu o console com 2,5–3 ms ocultos por quadro. A espera contada antes funcionava, por acaso, como margem. A margem passou a ser explícita (5 ms, calibrada contra o melhor bench por área), não o orçamento teórico.

## Resolução dinâmica (DRS)

Onde a GPU é o limite, a resolução interna cai por degraus de 0,25 até um mínimo configurável.

- **Sub-retângulo, sem realocar.** O alvo continua alocado na escala máxima; numa escala menor só a área renderizada muda. Recriar alvos invalidaria caches de nomes GL e alocaria memória no meio do jogo. É viável porque nada lê o alvo de volta para a memória do jogo; quem lê (cópia de display, filtros) recebe a extensão do conteúdo e uma borda de 2 texels replicada para os filtros bilineares e o FSR.
- **Troca no primeiro evento do quadro.** Nenhum quadro mistura duas escalas.
- **Sobe pela previsão.** Desce quando o par passa de ~85% do orçamento por 3 passos; sobe só quando o par **previsto** na escala de cima cabe em 80% por 60 passos. "Abaixo de 85% agora" a 2,75× pode ser 95% a 3×, e o controlador oscilaria.
- **Mesma medida que o governador.** Na primeira versão, o governador via a GPU oculta e descartava intermediários enquanto a DRS, olhando só o timer, achava que cabia. Dois controladores sobre o mesmo recurso devem decidir com a mesma medida.

Resultado no console (base 3×): refreshes sem imagem nova por janela de 150 quadros caíram de 39 para 4,6, igual ao 2× fixo, mantendo 3× nas áreas leves. FPS mínimo na área mais pesada: 51,1 → 60,0.

## O pacer e o relógio do display

O pacer dormia até o próximo múltiplo de 1/60 s **da CPU**. O display roda cerca de 0,2% mais devagar. Com swapchain FIFO de 3 imagens, nada "perde o vsync" no swap; a fila absorve, mas enche. Aí quem dita o ritmo passa a ser o acquire da imagem no meio do quadro, a render thread fica presa metade do tempo e, a cada volta da fase, sai um refresh sem imagem nova.

Dois relógios "de 60 Hz" nunca são o mesmo relógio. Quem apresenta deve seguir o relógio de quem exibe:

- O evento de vsync do serviço `vi` dá fase e período reais. No port, a **segunda abertura** do display padrão falhou com um código não documentado (a janela padrão da libnx já o tinha aberto).
- **Fonte reserva**: com a fila cheia, o acquire só retorna num vsync. O retorno de um acquire que bloqueou (≥ 1,5 ms) é um vsync mais uma latência curta, e um ajuste de envoltória inferior (o acordar nunca vem antes do vsync) recupera a fase.

No modelo, o pacer no vsync zerou os refreshes perdidos. No console, com a fonte reserva, ficou levemente pior que o pacer da CPU, e permaneceu desligado. O caso entra no guia porque o diagnóstico (swapchain cheia, deriva de fase) vale para qualquer port.

## Quadros em voo

Com um quadro em voo, um passo longo seguido de um intermediário curto não se compensa. Com dois, o modelo previa ganhos grandes, mas no console o heap corrompeu em 21 s: estado compartilhado da sessão supunha o jogo no máximo um quadro à frente. Mais folga na fila entre threads não é só um número; exige auditar o que os comandos capturam por referência, com TSan.

A alternativa segura foi menor: devolver o slot do quadro em voo quando o pacer **começa** a esperar (não depois do swap) e usar o prazo do pacer como relógio de refresh da thread do jogo. Na simulação, os refreshes perdidos por minuto caíram de 176 para 45 com passos de 14 ms.
