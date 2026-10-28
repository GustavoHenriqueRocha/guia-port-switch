# 12. Testes de regressão

Um bug do console custa um ciclo inteiro: build, cópia, jogar até reproduzir, baixar logs, analisar. A regra adotada no port: **todo bug corrigido ganha um teste que roda no host**, e toda decisão medida no console ganha uma guarda que impede desfazê-la sem querer.

## Lógica pura, sem GL e sem hardware

A maior parte do que decide desempenho foi escrita como **cabeçalho puro**, sem GL, sem libnx, testável em qualquer máquina:

- cache de estado GL (só emite a chamada que muda o valor: num quadro sintético de 400 draws, de 27,5 para 2,7 chamadas de estado por draw);
- cache de residência de texturas (30 minutos simulados);
- layout de threads, política de widescreen, escala e sub-retângulo da DRS;
- governador de interpolação, controlador da DRS, temporizador de GPU, detector de picos, relógio de vsync e a fonte reserva pelo acquire;
- mapeamento de enums e barreiras do backend deko3d.

O backend real só chama essas funções. Com isso, o comportamento é testado no host, e o console confirma o desempenho.

## Modelos do pipeline

Para pacing, o teste de unidade não basta: o problema está na interação entre o jogo, a render thread, a GPU, a swapchain e o display. O port tem um **simulador de cadência**: quadros com custos sorteados por cenário (área leve, área lenta, passo de 14 ms, display 0,2% mais lento, swapchain de 3), e o mesmo governador e pacer do produto. Ele responde perguntas antes do build:

- "devolver o slot no início do pacer ajuda?" (176 → 45 refreshes perdidos por minuto num cenário);
- "dois quadros em voo ajudam?" (sim no modelo; no console corrompeu o heap, e o teste passou a documentar por que a opção é ignorada);
- "qual margem usar?" (o replay por área com logs reais do console decidiu 5 ms).

Quando o console contradiz o modelo, o modelo ganha o parâmetro que faltava (a GPU "oculta" de 2,5–3 ms entrou assim).

## Exatidão bit a bit

Otimizações em código que tem resultado observável são provadas iguais ao original, não "parecidas":

- **Mixagem de áudio**: digest da saída igual no x86-64 e no AArch64.
- **Ponto flutuante do código gerado**: centenas de milhões de checagens no qemu-aarch64, em 16 combinações de modo de arredondamento, flush-to-zero e default-NaN. As mutações conhecidas precisam ser detectadas, senão o teste não prova nada.
- **Reescritas de funções quentes** à mão: um harness compila a versão original e a nova, roda milhões de casos aleatórios e de borda (ponteiro atravessando página, desalinhado, sobre a pilha, orçamento que acaba no meio) e exige estado, memória e contadores idênticos.

## Concorrência e duração

- ASan/UBSan e TSan nos testes da fila de comandos da render thread, do encerramento, do caminho de draws adiados e da interpolação.
- Soaks: minutos de quadros sintéticos contando bytes e alocações grandes por quadro.

## Guardas de bug

Alguns bugs não cabem num teste de unidade: uma instrução proibida no binário, um padrão perigoso no código, uma decisão de configuração. Para esses, um arquivo de **guardas** em Python roda no CI e no pre-commit, e cada guarda cita o bug que a motivou:

```python
def test_sem_cntvct_el0(self):
    """cntvct_el0 dá Data Abort no Horizon (o build morria na abertura)."""
    for arquivo in fontes_cpp():
        self.assertNotIn("cntvct_el0", ler(arquivo), arquivo)

def test_sem_detach(self):
    """pthread_detach retorna ENOSYS no newlib: std::thread::detach() lança."""
    for arquivo in fontes_do_switch():
        self.assertNotRegex(ler(arquivo), r"\.detach\(\)", arquivo)
```

Exemplos de guardas do port:

- nenhuma leitura de `cntvct_el0` (e, no ELF final, `objdump | grep -c cntvct_el0` = 0);
- nenhum `detach()` em código do Switch;
- ETC2 desligado por padrão (o "hardware" era fallback em CPU);
- dois quadros em voo ignorados (heap corrompido em 21 s);
- o pacer no vsync desligado por padrão (medido pior no console);
- a skip da tela de baixo nunca esvazia a composição (crash ao salvar);
- views do deko3d montadas no objeto guardado, folga depois de cada bloco de comandos.

Uma guarda de decisão não proíbe mudar de ideia: ela obriga quem muda a ler o motivo.

## O que não serve como teste de desempenho

- O **emulador**: variação de 5–10% entre rodadas, JIT frio, FPS dependente da janela estar visível.
- O **backend GL no Linux**: é o mesmo código e é ótimo para correção visual (remover um `glFinish` global por completion levou o Linux de 23,3 para 49,7 FPS), mas não diz nada sobre o desempenho no console.
- Um **bench de input** gravado (o mesmo trajeto reproduzido em cada build) serve para regressão de comportamento, não para medir velocidade no emulador.

Desempenho se mede no console, com o protocolo de A/B do [capítulo 8](08-medicao-de-frame-time.md#protocolo-de-ab).
