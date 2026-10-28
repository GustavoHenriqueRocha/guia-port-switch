"""Testes do gerador: ele roda, toda página sai e todo link interno resolve (arquivo e âncora)."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))

import gerar_site  # noqa: E402

RE_HREF = re.compile(r'(?:href|src)="([^"]+)"')
RE_ID = re.compile(r'id="([^"]+)"')


class TestGerador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.saida = Path(cls._tmp.name) / "_site"
        cls.paginas = gerar_site.gerar(RAIZ / "docs", cls.saida)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_uma_pagina_por_capitulo_e_indice(self):
        capitulos = sorted(p.stem for p in (RAIZ / "docs").glob("[0-9][0-9]-*.md"))
        self.assertGreaterEqual(len(capitulos), 10)
        geradas = sorted(p.stem for p in self.saida.glob("*.html") if p.name != "index.html")
        self.assertEqual(capitulos, geradas)
        self.assertTrue((self.saida / "index.html").is_file())
        self.assertTrue((self.saida / "estilo.css").is_file())

    def test_links_internos_resolvem(self):
        ids_cache: dict[Path, set[str]] = {}

        def ids(p: Path) -> set[str]:
            if p not in ids_cache:
                ids_cache[p] = set(RE_ID.findall(p.read_text(encoding="utf-8")))
            return ids_cache[p]

        quebrados = []
        for pagina in self.saida.glob("*.html"):
            for alvo in RE_HREF.findall(pagina.read_text(encoding="utf-8")):
                if re.match(r"^[a-z]+:", alvo):
                    continue
                caminho, _, ancora = alvo.partition("#")
                arquivo = (pagina.parent / caminho).resolve() if caminho else pagina
                if not arquivo.is_file():
                    quebrados.append(f"{pagina.name}: {alvo} (arquivo)")
                elif ancora and unquote(ancora) not in ids(arquivo):
                    quebrados.append(f"{pagina.name}: {alvo} (âncora)")
        self.assertEqual(quebrados, [])

    def test_navegacao_anterior_proximo(self):
        paginas = sorted(p for p in self.saida.glob("[0-9][0-9]-*.html"))
        primeira = paginas[0].read_text(encoding="utf-8")
        ultima = paginas[-1].read_text(encoding="utf-8")
        self.assertIn(f'href="{paginas[1].name}"', primeira)
        self.assertIn(f'href="{paginas[-2].name}"', ultima)
        self.assertNotIn("próximo →", ultima)

    def test_sem_markdown_cru_nos_capitulos(self):
        for pagina in self.saida.glob("[0-9][0-9]-*.html"):
            texto = pagina.read_text(encoding="utf-8")
            self.assertNotIn("```", texto, pagina.name)
            self.assertNotRegex(texto, r"\]\((?!\))", pagina.name)
            sem_pre = re.sub(r"<pre>.*?</pre>", "", texto, flags=re.S)
            self.assertNotIn("**", sem_pre, pagina.name)


class TestMarkdown(unittest.TestCase):
    def test_codigo_e_escapado(self):
        h = gerar_site.blocos(["```c", "if (a < b && c) {}", "```"], {})
        self.assertIn("a &lt; b &amp;&amp; c", h)
        self.assertIn('class="language-c"', h)

    def test_tabela_lista_e_inline(self):
        md = [
            "| a | b |",
            "|---|--:|",
            "| `x\\|y` | **n** |",
            "",
            "- um",
            "  - dois",
            "1. [link](02-x.md#ancora)",
        ]
        h = gerar_site.blocos(md, {})
        self.assertIn("<table>", h)
        self.assertIn('style="text-align:right"', h)
        self.assertIn("<strong>n</strong>", h)
        self.assertIn("<ul>", h)
        self.assertEqual(h.count("<ul>"), 2)
        self.assertIn('href="02-x.html#ancora"', h)

    def test_negrito_em_volta_de_codigo(self):
        self.assertEqual(
            gerar_site.inline("**`x_y` <b>** e *z*"),
            "<strong><code>x_y</code> &lt;b&gt;</strong> e <em>z</em>",
        )

    def test_slug_com_acento_e_duplicado(self):
        ids: dict[str, int] = {}
        h = gerar_site.blocos(["## Áudio no `audren`", "## Áudio no `audren`"], ids)
        self.assertIn('id="áudio-no-audren"', h)
        self.assertIn('id="áudio-no-audren-1"', h)


if __name__ == "__main__":
    unittest.main()
