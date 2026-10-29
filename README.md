# guia-port-switch

![pages](https://github.com/GustavoHenriqueRocha/guia-port-switch/actions/workflows/pages.yml/badge.svg)
![licença do texto](https://img.shields.io/badge/texto-CC%20BY%204.0-lightgrey)
![dependências](https://img.shields.io/badge/depend%C3%AAncias-nenhuma-39d98a)

Um guia técnico, em português, sobre levar um jogo nativo ou recompilado (vindo do 3DS ou do PC) para rodar como homebrew no **Nintendo Switch** com **frame time estável**: nenhum quadro acima de 16,7 ms em jogo normal, não só 60 FPS de média.

Não é teoria. Tudo saiu de um port real, medido no console: cada técnica vem com o problema que a motivou, o número que a justificou e, quando deu errado, o que se aprendeu.

```text
resolução dinâmica (base 3x), tour de 29 áreas no console
  refreshes sem imagem nova por janela de 150 quadros   39   ->  4,6
  FPS mínimo na área mais pesada                        51,1 -> 60,0
backend deko3d no lugar do Mesa, tour de 44 áreas
  CPU da render thread                                  34%  ->  20%
```

## De onde vem

O caso de estudo é o port para Switch do **TriAevum**, uma recompilação estática de *Ocarina of Time 3D*. O recompilador, o runtime e o renderizador são do projeto original, de [coccofresco](https://github.com/coccofresco/TriAevum). O port para o Switch, no fork [TriAevum-Switch](https://github.com/GustavoHenriqueRocha/TriAevum-Switch), é meu: a ideia de reunir técnicas de vários ports de Switch e testar o que funcionava neste jogo, o backend Switch e deko3d, o frame time, o áudio no console e a suíte de testes.

O guia não trata de obter jogos, ROMs, chaves ou firmware, nem de contornar proteções, e não contém assets de jogo. Os trechos de código são curtos e ilustrativos.

## Capítulos

| # | Capítulo | Assunto |
|---|---|---|
| 1 | [Introdução](docs/01-introducao.md) | escopo, créditos e hardware de referência |
| 2 | [Toolchain e armadilhas do Horizon](docs/02-toolchain-e-armadilhas.md) | devkitPro/libnx, newlib, `-ffast-math`, TLS, relógio, PGO com GCC, tempo de build |
| 3 | [Threads, núcleos e prioridades](docs/03-threads-no-horizon.md) | por que a render thread não roda, layout por papel |
| 4 | [GPU: Mesa/nouveau ou deko3d](docs/04-gpu-mesa-e-deko3d.md) | limites do Mesa 20.1, receita para deko3d, bugs e apresentação |
| 5 | [Patches do Mesa](docs/05-patches-do-mesa.md) | os sete patches e o porquê de cada um, glthread, `thrd_success` |
| 6 | [Cache de shaders](docs/06-cache-de-shaders.md) | zero compilações durante o jogo, no GL e no deko3d |
| 7 | [Orçamento de 16,7 ms e pacing](docs/07-orcamento-e-pacing.md) | interpolação, governador, resolução dinâmica, relógio do display |
| 8 | [Medição de frame time](docs/08-medicao-de-frame-time.md) | log de picos, GPU sem stall, tour por área, A/B, travamentos |
| 9 | [Memória](docs/09-memoria.md) | heap do newlib, memória de GPU limitada, testes de longa duração |
| 10 | [Áudio](docs/10-audio.md) | audren, 48 kHz, prioridade do SDL, `thrd_success` = 4 |
| 11 | [Deploy](docs/11-deploy.md) | nxlink, FTP, MTP e o que guardar de cada build |
| 12 | [Testes de regressão](docs/12-testes-de-regressao.md) | lógica pura, simulador de cadência, exatidão bit a bit, guardas |
| 13 | [Lições](docs/13-licoes.md) | o resumo para o próximo port |

## Bugs encontrados no devkitPro

Os dois foram relatados ao devkitPro em outubro de 2026 (SDL e pacman-packages). As issues foram removidas pelos mantenedores sem resposta, então o diagnóstico e a correção ficam documentados aqui:

- **SDL:** `SDL_THREAD_PRIORITY_TIME_CRITICAL` vira 0x3B no Horizon, abaixo do jogo, e o áudio picota sob carga. Ver [Áudio](docs/10-audio.md#a-prioridade-time_critical-do-sdl).
- **Mesa / newlib:** `thrd_success` vale 4 no newlib e o Mesa toma uma thread criada por falha. Ver [Patches do Mesa](docs/05-patches-do-mesa.md#0007-thrd_success-vale-4-no-newlib).

## Site

O site é gerado a partir de `docs/` por um script Python sem dependências e publicado no GitHub Pages pelo workflow `.github/workflows/pages.yml`.

```bash
python tools/gerar_site.py                    # gera _site/ (índice, capítulos, navegação, tema escuro)
python -m unittest discover -s tests -v       # o gerador roda e todo link interno resolve
python -m http.server -d _site 8000           # ver localmente
```

O conversor de Markdown cobre o que o guia usa (títulos com âncora, listas aninhadas, tabelas, citações, blocos de código, links entre capítulos). Os testes falham se um link para outro capítulo ou âncora não existir.

## Licença

Texto sob [CC BY 4.0](LICENSE); código do gerador sob [MIT](LICENSE-CODE).
