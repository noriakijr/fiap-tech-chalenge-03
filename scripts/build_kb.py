"""Constrói o índice FAISS a partir dos dados locais.

Lê todos os arquivos de `data/pubmedqa/` e `data/protocolos/`, gera embeddings
via OpenAI e persiste o índice em `data/faiss_index/`.

Uso:
    python -m scripts.build_kb                       # caminho default
    python -m scripts.build_kb --pubmedqa data/pubmedqa --protocolos data/protocolos --destino data/faiss_index
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Garante que o módulo app está no path quando executado como script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_openai import OpenAIEmbeddings

from app.core.config import get_settings
from app.rag.ingest_protocolos import carregar_protocolos
from app.rag.ingest_protocolos import para_documents as prot_docs
from app.rag.ingest_pubmedqa import carregar_pubmedqa
from app.rag.ingest_pubmedqa import construir_indice_faiss
from app.rag.ingest_pubmedqa import para_documents as pubmed_docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Constrói o índice FAISS da base de conhecimento.")
    parser.add_argument("--pubmedqa", default="data/pubmedqa", help="Caminho para os JSONs PubMedQA.")
    parser.add_argument("--protocolos", default="data/protocolos", help="Caminho para os JSONs de protocolos.")
    parser.add_argument("--destino", default=None, help="Onde salvar o índice (default: FAISS_INDEX_PATH do .env).")
    args = parser.parse_args()

    settings = get_settings()
    destino = Path(args.destino or settings.faiss_index_path)

    pubmedqa_path = Path(args.pubmedqa)
    protocolos_path = Path(args.protocolos)

    if not pubmedqa_path.exists():
        print(f"[ERRO] Diretório PubMedQA não encontrado: {pubmedqa_path}", file=sys.stderr)
        sys.exit(1)
    if not protocolos_path.exists():
        print(f"[ERRO] Diretório de protocolos não encontrado: {protocolos_path}", file=sys.stderr)
        sys.exit(1)

    # Carrega artigos PubMedQA
    arquivos_pubmed = sorted(pubmedqa_path.glob("*.json"))
    if not arquivos_pubmed:
        print(f"[AVISO] Nenhum arquivo JSON encontrado em {pubmedqa_path}.")
    all_artigos: list = []
    for arq in arquivos_pubmed:
        entradas = carregar_pubmedqa(arq)
        all_artigos.extend(pubmed_docs(entradas))
        print(f"  PubMedQA: {arq.name} → {len(entradas)} entradas")

    # Carrega protocolos
    pares = carregar_protocolos(protocolos_path)
    all_protocolos = prot_docs(pares)
    print(f"  Protocolos: {len(all_protocolos)} documentos carregados")

    todos = all_artigos + all_protocolos
    if not todos:
        print("[ERRO] Nenhum documento encontrado para indexar.", file=sys.stderr)
        sys.exit(1)

    print(f"\nTotal: {len(todos)} documentos ({len(all_artigos)} artigos + {len(all_protocolos)} protocolos)")
    print(f"Gerando embeddings e construindo índice FAISS em '{destino}'...")

    embeddings = OpenAIEmbeddings(model=settings.embeddings_model)
    construir_indice_faiss(todos, embeddings, destino)

    print(f"✓ Índice FAISS salvo em {destino}")


if __name__ == "__main__":
    main()
