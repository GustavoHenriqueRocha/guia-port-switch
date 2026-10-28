# 11. Deploy: nxlink, FTP e MTP

Um ciclo de medição no console tem três passos: levar o `.nro` (e às vezes dados) ao SD, rodar, trazer os logs de volta. Quanto mais curto esse ciclo, mais medições cabem num dia.

## nxlink: rodar sem copiar

O `nxlink` vem com o devkitPro. Com o Homebrew Menu aberto, apertar Y deixa o console esperando pela rede (netloader); do PC:

```sh
nxlink -s app.nro              # envia, roda e mostra o stdout/stderr no terminal
nxlink -a <ip-do-console> app.nro -- --argumento
```

É o caminho mais rápido para testes curtos e para ver `printf` em tempo real (`-s` liga o servidor de stdio; no app, `nxlinkStdio()` redireciona a saída). Limitações para um jogo grande:

- o `.nro` vai pela rede a cada execução (um jogo recompilado passa de 140 MB);
- o app roda a partir do netloader, não em modo título, então com memória de applet (ver [Memória](09-memoria.md#abra-pelo-modo-título)).

Para medir desempenho, o port sempre copiou o `.nro` para o SD e abriu pelo menu em modo título.

## FTP

Um menu de homebrew com servidor FTP (o projeto usou o do Sphaira) permite copiar e baixar arquivos do SD sem tirar o cartão:

```sh
curl -T app.nro ftp://<ip-do-console>:5000/switch/<jogo>/          # envia (sobrescreve)
curl ftp://<ip-do-console>:5000/switch/<jogo>/logs/perf.txt -o perf.txt
```

Cuidados:

- **Confira o tamanho** depois do envio (`curl -sI` e o `Content-Length` contra o arquivo local, ou o md5 de uma cópia baixada). Uma transferência interrompida deixa um `.nro` truncado que pode até abrir.
- **O FTP só existe com o menu aberto.** Ao abrir o jogo, ele fecha. Para automatizar algo durante o jogo, o comando tem de estar no SD antes (um roteiro lido na abertura, como o do [tour por área](08-medicao-de-frame-time.md#tour-por-área)).
- **O Wi-Fi dorme com a tela apagada**: o FTP some até o console acordar.
- O IP do console muda com a rede. Um script que varre a porta do FTP na rede local resolve.

## MTP

Pelo cabo USB, o mesmo menu expõe o SD por MTP:

```sh
gio mount mtp://<dispositivo>/
gio remove "mtp://<dispositivo>/microSD card/switch/<jogo>/app.nro"
gio copy app.nro "mtp://<dispositivo>/microSD card/switch/<jogo>/"
```

O MTP **não sobrescreve**: remova antes de copiar. É mais estável que o FTP para arquivos grandes.

## Rótulo por build

Com vários builds de teste no SD, é fácil abrir o errado. O port grava, no próprio `.nro`, o nome e a versão exibidos no menu e uma faixa no ícone, sem recompilar (o NACP e o ícone ficam na seção de assets no fim do arquivo). E o log de cada backend imprime o rótulo do build na segunda linha: se não bate, o `.nro` no SD não é o novo.

## O que guardar de cada envio

- O `.nro` com nome e md5.
- O **`.elf` exato** correspondente, para simbolizar crash reports (ver [Medição](08-medicao-de-frame-time.md#crash-reports-do-atmosphère)).
- O commit e as opções de build.
- Os logs da sessão, numa pasta com o rótulo do build.

## Limpeza

Builds antigos no SD confundem e ocupam espaço. Mantenha só os que estão em uso, e remova também arquivos de configuração de teste que deixam o jogo mais lento (perfis, varreduras de heap) quando terminar a medição.
