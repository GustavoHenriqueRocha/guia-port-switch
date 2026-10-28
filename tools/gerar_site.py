#!/usr/bin/env python3
"""Gera o site estático do guia a partir de docs/*.md, só com a biblioteca padrão.

    python tools/gerar_site.py [--docs docs] [--saida _site]

Cada capítulo vira uma página com navegação anterior/próximo; index.html lista todos.
O conversor de Markdown cobre o que o guia usa: títulos, parágrafos, listas (aninhadas),
citações, tabelas, blocos de código, código inline, negrito, itálico e links. Links para
outro capítulo (`02-x.md#ancora`) viram `02-x.html#ancora`.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TITULO_SITE = "Guia de port para o Nintendo Switch"

# --------------------------------------------------------------------------- inline


def slug(texto: str) -> str:
    """Âncora de um título, no estilo do GitHub (mantém acentos)."""
    texto = re.sub(r"[`*]", "", texto).strip().lower()
    texto = re.sub(r"[^\w\s-]", "", texto)
    return re.sub(r"\s", "-", texto)


def _link(url: str) -> str:
    if re.match(r"^[a-z]+:", url) or url.startswith("#"):
        return url
    return re.sub(r"\.md(?=$|#)", ".html", url)


def inline(texto: str) -> str:
    codigos: list[str] = []

    def guardar(m: re.Match) -> str:
        codigos.append("<code>" + html.escape(m.group(1), quote=False) + "</code>")
        return f"\x00{len(codigos) - 1}\x00"

    p = re.sub(r"`([^`]+)`", guardar, texto)
    p = html.escape(p, quote=False)
    p = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f'<a href="{html.escape(_link(m.group(2)))}">{m.group(1)}</a>',
        p,
    )
    p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
    p = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", p)
    return re.sub(r"\x00(\d+)\x00", lambda m: codigos[int(m.group(1))], p)


# --------------------------------------------------------------------------- blocos

RE_ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
RE_TITULO = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _eh_tabela(linhas: list[str], i: int) -> bool:
    return (
        linhas[i].lstrip().startswith("|")
        and i + 1 < len(linhas)
        and re.match(r"^\s*\|?\s*:?-{3,}", linhas[i + 1]) is not None
    )


def _celulas(linha: str) -> list[str]:
    linha = linha.strip()
    if linha.startswith("|"):
        linha = linha[1:]
    if linha.endswith("|") and not linha.endswith("\\|"):
        linha = linha[:-1]
    celulas = re.split(r"(?<!\\)\|", linha)
    return [c.strip().replace("\\|", "|") for c in celulas]


def _inicia_bloco(linha: str) -> bool:
    return bool(
        linha.startswith("```")
        or RE_TITULO.match(linha)
        or linha.lstrip().startswith(">")
        or RE_ITEM.match(linha)
        or re.match(r"^\s*(-{3,}|\*{3,})\s*$", linha)
    )


def _lista(linhas: list[str], i: int, ids: dict[str, int]) -> tuple[str, int]:
    m = RE_ITEM.match(linhas[i])
    assert m
    base = len(m.group(1))
    ordenada = m.group(2)[0].isdigit()
    itens: list[list[str]] = []
    while i < len(linhas):
        linha = linhas[i]
        m = RE_ITEM.match(linha)
        if m and len(m.group(1)) == base and m.group(2)[0].isdigit() == ordenada:
            recuo = len(m.group(1)) + len(m.group(2)) + 1
            itens.append([m.group(3)])
            i += 1
            while i < len(linhas):
                prox = linhas[i]
                if not prox.strip():
                    seguinte = linhas[i + 1] if i + 1 < len(linhas) else ""
                    if seguinte.strip() and len(seguinte) - len(seguinte.lstrip()) > base:
                        itens[-1].append("")
                        i += 1
                        continue
                    break
                ind = len(prox) - len(prox.lstrip())
                if ind > base:
                    itens[-1].append(prox[min(ind, recuo):])
                    i += 1
                elif RE_ITEM.match(prox) or _inicia_bloco(prox):
                    break
                else:  # continuação preguiçosa do parágrafo
                    itens[-1].append(prox.strip())
                    i += 1
            continue
        if not linha.strip() and i + 1 < len(linhas):
            m2 = RE_ITEM.match(linhas[i + 1])
            if m2 and len(m2.group(1)) == base and m2.group(2)[0].isdigit() == ordenada:
                i += 1
                continue
        break
    tag = "ol" if ordenada else "ul"
    partes = [f"<{tag}>"]
    for corpo in itens:
        conteudo = blocos(corpo, ids)
        if conteudo.startswith("<p>") and conteudo.count("<p>") == 1:
            conteudo = conteudo.replace("<p>", "", 1).replace("</p>", "", 1)
        partes.append(f"<li>{conteudo}</li>")
    partes.append(f"</{tag}>")
    return "\n".join(partes), i


def blocos(linhas: list[str], ids: dict[str, int], titulos: list | None = None) -> str:
    saida: list[str] = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        if not linha.strip():
            i += 1
            continue
        if linha.startswith("```"):
            lang = linha[3:].strip()
            i += 1
            corpo = []
            while i < len(linhas) and not linhas[i].startswith("```"):
                corpo.append(linhas[i])
                i += 1
            i += 1
            classe = f' class="language-{html.escape(lang)}"' if lang else ""
            saida.append(f"<pre><code{classe}>" + html.escape("\n".join(corpo), quote=False) + "</code></pre>")
            continue
        m = RE_TITULO.match(linha)
        if m:
            nivel = len(m.group(1))
            texto = m.group(2)
            ancora = slug(texto)
            if ancora in ids:
                ids[ancora] += 1
                ancora = f"{ancora}-{ids[ancora]}"
            else:
                ids[ancora] = 0
            if titulos is not None:
                titulos.append((nivel, texto, ancora))
            saida.append(f'<h{nivel} id="{ancora}">{inline(texto)}</h{nivel}>')
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", linha):
            saida.append("<hr>")
            i += 1
            continue
        if linha.lstrip().startswith(">"):
            citacao = []
            while i < len(linhas) and linhas[i].lstrip().startswith(">"):
                citacao.append(re.sub(r"^\s*>\s?", "", linhas[i]))
                i += 1
            saida.append("<blockquote>\n" + blocos(citacao, ids) + "\n</blockquote>")
            continue
        if _eh_tabela(linhas, i):
            cab = _celulas(linhas[i])
            alinhamentos = []
            for c in _celulas(linhas[i + 1]):
                if c.startswith(":") and c.endswith(":"):
                    alinhamentos.append("center")
                elif c.endswith(":"):
                    alinhamentos.append("right")
                else:
                    alinhamentos.append("")
            i += 2
            corpo = []
            while i < len(linhas) and linhas[i].lstrip().startswith("|"):
                corpo.append(_celulas(linhas[i]))
                i += 1

            def celula(tag: str, texto: str, col: int) -> str:
                al = alinhamentos[col] if col < len(alinhamentos) else ""
                estilo = f' style="text-align:{al}"' if al else ""
                return f"<{tag}{estilo}>{inline(texto)}</{tag}>"

            t = ['<div class="tabela"><table>', "<thead><tr>"]
            t += [celula("th", c, n) for n, c in enumerate(cab)]
            t.append("</tr></thead><tbody>")
            for linha_t in corpo:
                t.append("<tr>" + "".join(celula("td", c, n) for n, c in enumerate(linha_t)) + "</tr>")
            t.append("</tbody></table></div>")
            saida.append("".join(t))
            continue
        if RE_ITEM.match(linha):
            lista, i = _lista(linhas, i, ids)
            saida.append(lista)
            continue
        paragrafo = [linha.strip()]
        i += 1
        while i < len(linhas) and linhas[i].strip() and not _inicia_bloco(linhas[i]) and not _eh_tabela(linhas, i):
            paragrafo.append(linhas[i].strip())
            i += 1
        saida.append("<p>" + inline(" ".join(paragrafo)) + "</p>")
    return "\n".join(saida)


# --------------------------------------------------------------------------- páginas


@dataclass
class Capitulo:
    fonte: Path
    destino: str
    titulo: str
    resumo: str
    corpo: str
    secoes: list


def ler_capitulo(caminho: Path) -> Capitulo:
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    titulos: list = []
    corpo = blocos(linhas, {}, titulos)
    titulo = next((t for n, t, _ in titulos if n == 1), caminho.stem)
    resumo = ""
    for linha in linhas:
        s = linha.strip()
        if s and not s.startswith(("#", ">", "|", "-", "```")):
            resumo = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
            break
    secoes = [(t, a) for n, t, a in titulos if n == 2]
    return Capitulo(caminho, caminho.stem + ".html", re.sub(r"`", "", titulo), resumo, corpo, secoes)


CSS = """
:root{--fundo:#0f1216;--painel:#161b22;--texto:#d7dde4;--fraco:#8b96a3;--borda:#2a313b;
--destaque:#5fb3f9;--codigo:#1b2129;--marca:#e06c75}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--fundo);color:var(--texto);font:16px/1.65 system-ui,-apple-system,
"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
a{color:var(--destaque);text-decoration:none}a:hover{text-decoration:underline}
header.topo{border-bottom:1px solid var(--borda);background:var(--painel)}
header.topo div{max-width:880px;margin:0 auto;padding:12px 16px;display:flex;gap:12px;
align-items:baseline;flex-wrap:wrap}
header.topo a.marca{color:var(--texto);font-weight:600}
main{max-width:880px;margin:0 auto;padding:24px 16px 48px}
h1,h2,h3,h4{line-height:1.25;margin:1.6em 0 .6em}h1{margin-top:.4em;font-size:2rem}
h2{font-size:1.45rem;border-bottom:1px solid var(--borda);padding-bottom:.25em}
h3{font-size:1.15rem}
code{font:0.9em/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--codigo);
padding:.1em .35em;border-radius:4px}
pre{background:var(--codigo);border:1px solid var(--borda);border-radius:8px;padding:12px 14px;
overflow-x:auto}
pre code{background:none;padding:0;font-size:.86em}
blockquote{margin:1em 0;padding:.4em 1em;border-left:3px solid var(--marca);background:var(--painel);
border-radius:0 6px 6px 0}
.tabela{overflow-x:auto;margin:1em 0}
table{border-collapse:collapse;width:100%;font-size:.93em}
th,td{border:1px solid var(--borda);padding:6px 9px;vertical-align:top}
th{background:var(--painel);text-align:left}
hr{border:0;border-top:1px solid var(--borda);margin:2em 0}
nav.passos{display:flex;justify-content:space-between;gap:12px;margin-top:3em;padding-top:1em;
border-top:1px solid var(--borda);flex-wrap:wrap}
nav.passos a{display:block;max-width:48%}
nav.passos .rot{display:block;color:var(--fraco);font-size:.8em}
ol.capitulos{padding-left:1.4em}ol.capitulos li{margin:.6em 0}
ol.capitulos .res{display:block;color:var(--fraco);font-size:.92em}
footer{color:var(--fraco);font-size:.85em;max-width:880px;margin:0 auto;padding:0 16px 32px}
@media (max-width:600px){h1{font-size:1.6rem}nav.passos a{max-width:100%}}
"""


def pagina(titulo: str, corpo: str, navegacao: str = "") -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<link rel="stylesheet" href="estilo.css">
</head>
<body>
<header class="topo"><div><a class="marca" href="index.html">{html.escape(TITULO_SITE)}</a></div></header>
<main>
{corpo}
{navegacao}
</main>
<footer>Texto sob CC BY 4.0; código do gerador sob MIT. Gerado por tools/gerar_site.py.</footer>
</body>
</html>
"""


def navegacao(anterior: Capitulo | None, proximo: Capitulo | None) -> str:
    partes = ['<nav class="passos">']
    if anterior:
        partes.append(f'<a href="{anterior.destino}"><span class="rot">← anterior</span>{html.escape(anterior.titulo)}</a>')
    else:
        partes.append('<a href="index.html"><span class="rot">← início</span>Sumário</a>')
    if proximo:
        partes.append(f'<a href="{proximo.destino}" style="text-align:right"><span class="rot">próximo →</span>{html.escape(proximo.titulo)}</a>')
    partes.append("</nav>")
    return "\n".join(partes)


def gerar(docs: Path, saida: Path) -> list[Path]:
    fontes = sorted(p for p in docs.glob("*.md") if re.match(r"^\d{2}-", p.name))
    if not fontes:
        raise SystemExit(f"nenhum capítulo NN-*.md em {docs}")
    capitulos = [ler_capitulo(p) for p in fontes]
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    (saida / "estilo.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    (saida / ".nojekyll").write_text("", encoding="utf-8")
    geradas = []
    for n, cap in enumerate(capitulos):
        ant = capitulos[n - 1] if n > 0 else None
        prox = capitulos[n + 1] if n + 1 < len(capitulos) else None
        destino = saida / cap.destino
        destino.write_text(pagina(f"{cap.titulo} · {TITULO_SITE}", cap.corpo, navegacao(ant, prox)), encoding="utf-8")
        geradas.append(destino)
    itens = []
    for cap in capitulos:
        itens.append(
            f'<li><a href="{cap.destino}">{html.escape(cap.titulo)}</a>'
            f'<span class="res">{inline(cap.resumo)}</span></li>'
        )
    indice = (
        f"<h1>{html.escape(TITULO_SITE)}</h1>\n"
        "<p>Como levar um jogo nativo ou recompilado (vindo do 3DS ou do PC) para rodar como homebrew "
        "no Nintendo Switch com frame time estável. Baseado num port real; cada técnica vem com o "
        "problema que a motivou e o número que a justificou.</p>\n"
        '<h2 id="capitulos">Capítulos</h2>\n<ol class="capitulos">\n' + "\n".join(itens) + "\n</ol>"
    )
    primeiro = capitulos[0]
    nav = f'<nav class="passos"><span></span><a href="{primeiro.destino}" style="text-align:right"><span class="rot">começar →</span>{html.escape(primeiro.titulo)}</a></nav>'
    (saida / "index.html").write_text(pagina(TITULO_SITE, indice, nav), encoding="utf-8")
    geradas.append(saida / "index.html")
    return geradas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--docs", type=Path, default=RAIZ / "docs")
    ap.add_argument("--saida", type=Path, default=RAIZ / "_site")
    args = ap.parse_args(argv)
    geradas = gerar(args.docs, args.saida)
    print(f"{len(geradas)} páginas em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
