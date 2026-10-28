# 9. Memória: heap do newlib e memória de GPU

No Switch, CPU e GPU dividem a mesma memória, e o homebrew em modo aplicação tem uma fatia fixa dela. Os problemas de memória do port não apareceram no primeiro minuto: apareceram aos 3, aos 8 e aos 21 minutos. Por isso a regra deste capítulo é: **tudo que roda o tempo todo precisa de um teste de longa duração antes de ir ao console.**

## Abra pelo modo título

Abrir o Homebrew Menu pelo álbum dá ao homebrew uma fração da memória (modo applet). Para um jogo, abra em **modo título** (segurando R ao abrir um jogo instalado). Diagnosticar "falta de memória" sem confirmar o modo de abertura é perder tempo.

## O heap do newlib

O `malloc` do newlib tem um **lock global**, compartilhado com o Mesa, e o `libdrm_nouveau` aloca cada buffer de GPU com `memalign`. Blocos grandes de tamanhos variados a cada quadro fragmentam o heap: numa sessão de 8,5 minutos a 60 FPS, a arena foi de 631 MB a 1659 MB com cerca de 700 MB realmente em uso.

Regras adotadas:

- **Nada de alocação grande por quadro.** Pools que devolvem a memória limpa, vetores que mantêm a capacidade, lotes reciclados.
- **Contar alocações por draw.** O worker que prepara os draws alocava 152 KiB por draw (contra 34 KiB do caminho serial) e degradava de 3,9 para 89 ms por quadro em 3 minutos. Um teste trava o número de `malloc` por draw (5, depois 2–3) para que não volte a subir.
- **Anéis de upload até 2 MiB.** Até esse tamanho o nouveau subaloca de slabs; acima, cada orphan de buffer vira um `memalign`.
- **`mallinfo()` só sob demanda.** Ele percorre o heap inteiro segurando o lock (ver [Medição](08-medicao-de-frame-time.md#medir-sem-atrapalhar)).

### Heap corrompido: o crash não acusa o culpado

Um Data Abort dentro do `free` do Mesa, ao apagar uma textura, parecia bug no cache de texturas do port. Os registradores mostravam uma struct do Mesa com um ponteiro ímpar e desalinhado: memória sobrescrita antes, por outra coisa, no mesmo heap. A parte do chamador foi provada correta com um soak de host sob ASan (sessão simulada de 10 minutos, cada textura liberada exatamente uma vez e nunca em uso).

Para achar corrupção perto de onde ela acontece, o port tem uma varredura **limitada** dos bins do newlib a cada N janelas, que avisa cerca de 5 s depois.

## Memória de GPU limitada

Sem limite, o cache de texturas cresce até o console cair: com 60 FPS isso levava cerca de 8 minutos. O cache de residência:

- Indexa texturas **por conteúdo**, com LRU e um orçamento configurável (padrão 96 MB).
- Despeja só texturas fora de uso há N quadros, e só depois do fence do quadro que as usou.
- Trata falta de memória como **não fatal**: o draw é pulado e contado, e a próxima janela do log mostra.
- Usa anéis de upload com `map` sem sincronização para vértices, índices e uniforms.

O mesmo orçamento e a mesma política de despejo foram reaproveitados no backend deko3d, onde cada textura é um `DkMemBlock` próprio liberado só depois dos quadros em voo.

## Structs grandes custam banda

Uma seção da render thread levava 2 ms por quadro e parecia "plano de draw atrasado". Os contadores mostraram que nada atrasava: o custo era **copiar** os planos prontos. Cada plano tinha 15.712 bytes, 122 por quadro, frios no cache (o lote e o vetor do quadro somavam mais que os 2 MB de L2).

A primeira ideia foi guardar planos por ponteiro, uma refatoração de cerca de 113 acessos. Antes disso, a pergunta certa: **quais campos alguém lê?** 39% do struct era um objeto do qual só três campos eram usados. Trocar o tipo do membro por um struct só com esses campos é exato (o compilador recusa qualquer leitura do que saiu) e levou o plano a 9.568 bytes. Um `static_assert` no teste trava o tamanho máximo.

## Teste de longa duração

Antes de ir ao console, cada mudança que roda o tempo todo passa por um soak de host:

- quadros sintéticos por vários minutos simulados, contando bytes e número de alocações ≥ 256 KiB por quadro (o soak do caminho de draws foi de 12 MB e 4,8 alocações grandes por quadro para 0,24 MB e zero);
- o cache de residência por 30 minutos simulados;
- os mesmos testes sob ASan/UBSan e TSan.

E no console, uma sessão de 30 minutos ou mais olhando os campos de memória do `perf.txt`: arena, pico, memória do processo e de GPU devem ficar planos.
